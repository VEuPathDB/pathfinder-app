"""VERIFY's digest names only genes and sources this turn read, and is refused
once per check with one sentence per departure."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import RunContext
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.ai.agents.verification_digest import hold_the_digest_to_the_evidence
from pathfinder.ai.graph.runtime import AgentDeps, VerificationScope
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.domain.evidence import WithheldEvidence
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_READ_GENE = "PF3D7_1133400"
_UNREAD_GENE = "PF3D7_0102200"
_READ_DOI = "10.1038/nature03069"


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "exported proteins", "plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(id="step_sp", search_name="GenesWithSignalPeptide")
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def _context() -> RunContext[AgentDeps]:
    ctx = agent_run_context(strategy_session=_session())
    ctx.deps.verification_scope = VerificationScope(
        check_id="call_v1", messages=["genes with a signal peptide"]
    )
    markers = ctx.deps.turn_markers
    markers.record_retrieved_source(
        f"https://qa.plasmodb.org/plasmo.qa/app/record/gene/{_READ_GENE}"
    )
    markers.record_retrieved_source(f"https://doi.org/{_READ_DOI}")
    return ctx


def _gene(gene_id: str, fits: str) -> dict[str, Any]:
    return {"geneId": gene_id, "fits": fits, "why": "its record shows a signal peptide"}


def _delta(
    prose: str = "The strategy answers the request.", **review: Any
) -> VerificationDelta:
    return VerificationDelta.model_validate(
        {"digest": {"prose": prose, "review": review}}
    )


def _refusal(delta: VerificationDelta) -> str:
    with pytest.raises(ModelRetry) as refused:
        hold_the_digest_to_the_evidence(_context(), delta)
    return str(refused.value)


def test_a_digest_of_what_the_turn_read_passes() -> None:
    delta = _delta(
        sampledGenes=[_gene(_READ_GENE, "yes")],
        sources=[
            {
                "kind": "literature",
                "label": "Exported proteins",
                "doi": _READ_DOI,
                "why": "it lists them",
            }
        ],
        requirements=[
            {
                "text": "genes with a signal peptide",
                "turn": 1,
                "answeredBy": ["step_sp"],
                "how": "search",
                "status": "met",
            }
        ],
    )

    assert hold_the_digest_to_the_evidence(_context(), delta) is delta


def test_a_sampled_gene_whose_record_the_turn_did_not_read_is_refused() -> None:
    refusal = _refusal(_delta(sampledGenes=[_gene(_UNREAD_GENE, "yes")]))

    assert refusal.startswith(
        f"The review lists sampled gene `{_UNREAD_GENE}`, and no read_gene_record "
        "call of this turn read its record."
    )


def test_a_source_no_read_returned_is_refused() -> None:
    refusal = _refusal(
        _delta(
            sources=[
                {
                    "kind": "web",
                    "label": "A page",
                    "url": "https://example.org/x",
                    "why": "it says so",
                }
            ]
        )
    )

    assert refusal.startswith(
        "The review cites https://example.org/x, and no read of this turn returned it."
    )


_UNREAD = WithheldEvidence(
    kind="sampled_gene",
    sentence=(
        f"The review lists sampled gene `{_UNREAD_GENE}`, and no read_gene_record "
        "call of this turn read its record."
    ),
)


def _sampled() -> VerificationDelta:
    return _delta(sampledGenes=[_gene(_READ_GENE, "yes"), _gene(_UNREAD_GENE, "yes")])


def _withheld_from(
    delta: VerificationDelta,
) -> tuple[list[str], list[WithheldEvidence]]:
    review = delta.digest.review
    return [g.gene_id for g in review.sampled_genes], list(review.withheld)


def test_the_digest_is_refused_once_per_check_then_loses_the_unread_gene() -> None:
    ctx = _context()
    with pytest.raises(ModelRetry):
        hold_the_digest_to_the_evidence(ctx, _sampled())

    held = hold_the_digest_to_the_evidence(ctx, _sampled())

    assert isinstance(held, VerificationDelta)
    assert _withheld_from(held) == ([_READ_GENE], [_UNREAD])
    assert ctx.deps.turn_markers.refused_digests == ["call_v1"]


def test_the_last_answer_the_run_allows_loses_the_unread_gene() -> None:
    ctx = _context()

    held = hold_the_digest_to_the_evidence(
        replace(ctx, retry=ctx.max_retries), _sampled()
    )

    assert isinstance(held, VerificationDelta)
    assert _withheld_from(held) == ([_READ_GENE], [_UNREAD])


def test_the_digest_past_the_pass_s_refusals_loses_the_unread_gene() -> None:
    ctx = _context()
    ctx.deps.agent_state.refusals = REFUSALS_PER_CHECK

    held = hold_the_digest_to_the_evidence(ctx, _sampled())

    assert isinstance(held, VerificationDelta)
    assert _withheld_from(held) == ([_READ_GENE], [_UNREAD])


def test_a_source_that_cannot_be_opened_is_taken_off_the_review() -> None:
    ctx = _context()
    ctx.deps.agent_state.refusals = REFUSALS_PER_CHECK
    delta = _delta(sources=[{"kind": "web", "label": "A page", "why": "it says so"}])

    held = hold_the_digest_to_the_evidence(ctx, delta)

    assert isinstance(held, VerificationDelta)
    assert (held.digest.review.sources, held.digest.review.withheld) == (
        [],
        [
            WithheldEvidence(
                kind="source",
                sentence="The review cites 'A page', which carries no url, DOI or PMID.",
            )
        ],
    )


async def test_verify_answering_the_unread_gene_every_time_ends_on_its_review() -> None:
    told: list[str] = []
    answer = {
        "digest": {
            "disposition": "done",
            "prose": "The strategy answers the request.",
            "reason": "Read the sample.",
            "success": True,
            "review": {"sampledGenes": [_gene(_UNREAD_GENE, "yes")]},
        }
    }

    def _verify(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        told.extend(
            str(p.content) for p in last.parts if isinstance(p, RetryPromptPart)
        )
        return ModelResponse(parts=[ToolCallPart("final_result", answer)])

    deps = _context().deps
    agent = build_verification_agent()
    with agent.override(model=FunctionModel(_verify, model_name="scripted")):
        run = await agent.run("VERIFY work order: check it", deps=deps)

    assert isinstance(run.output, VerificationDelta)
    assert len(told) == 1
    assert _withheld_from(run.output) == ([], [_UNREAD])
