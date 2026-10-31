"""VERIFY's review is corrected once when it states what the turn did not read:
a sampled-gene count its own sample does not hold, a gene whose record no read
returned, a source no read retrieved, or a message the request does not have."""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import ToolCallPart
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.agents.verification import (
    _VERIFICATION_INSTRUCTIONS,
    build_verification_agent,
)
from pathfinder.ai.graph.runtime import VerificationScope
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests.unit.ai.lead.conftest import RetryRecordingScript
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_RECORD = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/{}"
_READ = ("PF3D7_0102200", "PF3D7_0935800")
_PAPER = "10.1038/nature12970"


def _gene(gene_id: str, fits: str) -> dict[str, str]:
    return {
        "geneId": gene_id,
        "product": "ring-infected erythrocyte surface antigen",
        "organism": "Plasmodium falciparum 3D7",
        "fits": fits,
        "why": "the product is an exported surface antigen",
    }


def _digest(prose: str, review: dict[str, Any]) -> dict[str, Any]:
    return {"digest": {"prose": prose, "review": review}}


def _session(steps: tuple[str, ...]) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Exported", site_id="plasmodb")
    for step_id in steps:
        graph.steps.update(
            flatten_tree(StrategyStepNode(id=step_id, search_name="GenesByText"))
        )
    session.graph = graph
    return session


async def _verified(
    prose: str,
    review: dict[str, Any],
    *,
    retrieved: tuple[str, ...] = (),
    steps: tuple[str, ...] = ("s1",),
) -> tuple[VerificationDelta, list[str]]:
    ctx = agent_run_context(strategy_session=_session(steps))
    for gene_id in _READ:
        ctx.deps.turn_markers.record_retrieved_source(_RECORD.format(gene_id))
    for reference in retrieved:
        ctx.deps.turn_markers.record_retrieved_source(reference)
    ctx.deps.verification_scope = VerificationScope(
        check_id="call_v1", messages=["Exported P. falciparum 3D7 genes."]
    )
    script = RetryRecordingScript(
        ToolCallPart(
            tool_name="final_result",
            args=_digest(prose, review),
            tool_call_id="call_final",
        )
    )
    agent = build_verification_agent()
    with agent.override(model=script.model()):
        result = await agent.run("Verify the exported genes.", deps=ctx.deps)
    assert isinstance(result.output, VerificationDelta)
    return result.output, script.retries


async def test_a_gene_whose_record_no_read_returned_is_refused() -> None:
    review = {"sampledGenes": [_gene("PF3D7_1133400", "yes")]}

    _digest_out, retries = await _verified("One gene was read.", review)

    assert len(retries) == 1
    assert (
        "The review lists sampled gene `PF3D7_1133400`, and no read_gene_record "
        "call of this turn read its record."
    ) in retries[0]


async def test_a_source_no_read_retrieved_is_refused() -> None:
    review = {
        "sources": [
            {
                "kind": "literature",
                "label": "Exportome",
                "doi": _PAPER,
                "why": "lists exported proteins",
            }
        ]
    }

    _digest_out, retries = await _verified("One paper backs it.", review)

    assert len(retries) == 1
    assert (
        f"The review cites {_PAPER}, and no read of this turn returned it."
    ) in retries[0]


async def test_a_review_the_turn_backs_passes() -> None:
    review = {
        "sampledGenes": [_gene(_READ[0], "yes"), _gene(_READ[1], "yes")],
        "sources": [
            {
                "kind": "literature",
                "label": "Exportome",
                "doi": _PAPER,
                "why": "lists exported proteins",
            }
        ],
    }

    digest, retries = await _verified(
        "All 2 sampled genes fit.", review, retrieved=(_PAPER,)
    )

    assert retries == []
    assert [g.gene_id for g in digest.digest.review.sampled_genes] == list(_READ)


def test_membership_in_the_strategy_is_not_a_genes_fit() -> None:
    assert (
        "Membership in the strategy is not evidence of fit: a gene fits only when "
        "its record shows what the request names, and is ``unclear`` when the "
        "record does not show it."
    ) in " ".join(_VERIFICATION_INSTRUCTIONS.split())
