"""VERIFY's digest names only genes, sources, messages and steps this turn read,
and is refused once per check with one sentence per departure."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.agents.verification import hold_the_digest_to_the_evidence
from pathfinder.ai.graph.runtime import AgentDeps, VerificationScope
from pathfinder.ai.lead.deltas import VerificationDelta
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
        f"https://plasmodb.org/plasmo/app/record/gene/{_READ_GENE}"
    )
    markers.record_retrieved_source(f"https://doi.org/{_READ_DOI}")
    return ctx


def _gene(gene_id: str, fits: str) -> dict[str, Any]:
    return {"geneId": gene_id, "fits": fits, "why": "its record shows a signal peptide"}


def _delta(
    prose: str = "The strategy answers the request.", **review: Any
) -> VerificationDelta:
    return VerificationDelta.model_validate(
        {
            "digest": {
                "disposition": "done",
                "prose": prose,
                "reason": "Read the sample.",
                "success": True,
                "review": review,
            }
        }
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


def test_a_requirement_naming_a_message_the_request_lacks_is_refused() -> None:
    row = {
        "text": "genes with a signal peptide",
        "turn": 3,
        "answeredBy": ["step_sp"],
        "how": "search",
        "status": "met",
    }

    assert _refusal(_delta(requirements=[row])).startswith(
        "The requirement 'genes with a signal peptide' names message 3, and the "
        "request has 1 message."
    )


def test_a_requirement_answered_by_an_unknown_step_is_refused() -> None:
    row = {
        "text": "genes with a signal peptide",
        "turn": 1,
        "answeredBy": ["step_zz"],
        "how": "search",
        "status": "met",
    }

    assert _refusal(_delta(requirements=[row])).startswith(
        "The requirement 'genes with a signal peptide' is answered by step_zz, which "
        "names no step of the strategy; it holds step_sp."
    )


def test_a_sample_count_the_sample_does_not_hold_is_refused() -> None:
    delta = _delta(
        "**2** of 2 sampled genes fit.",
        sampledGenes=[_gene(_READ_GENE, "yes")],
    )

    assert _refusal(delta).startswith(
        "The reply says 2 of 2 sampled genes fit; the check sampled 1 genes: 1 fit, "
        "0 do not fit, 0 unclear."
    )


def test_the_digest_is_refused_once_per_check() -> None:
    ctx = _context()
    delta = _delta(sampledGenes=[_gene(_UNREAD_GENE, "yes")])
    with pytest.raises(ModelRetry):
        hold_the_digest_to_the_evidence(ctx, delta)

    assert hold_the_digest_to_the_evidence(ctx, delta) is delta
    assert ctx.deps.turn_markers.refused_digests == ["call_v1"]
