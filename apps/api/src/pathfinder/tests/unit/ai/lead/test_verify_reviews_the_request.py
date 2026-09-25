"""VERIFY is handed every message of the request and the root it samples, and
its review reaches the verdict and the card as the record lets it stand."""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import evidence_card, verify_dispatch
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import (
    RootSample,
    run_verification,
    verification_scope,
    work_order,
)
from pathfinder.domain.evidence import SAMPLED_GENE_LIMIT
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.site_counts import SiteCounts
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
    requirement,
)

_ASKED = "P. falciparum 3D7 genes with a signal peptide"
_ADDED = "Also require at least 2 transmembrane domains."
_ROOT = 440299573
_STRATEGY = 300125410
_RECORD = "https://plasmodb.org/plasmo/app/record/gene/{}"

pytestmark = pytest.mark.usefixtures("collector")


def _deps(*, unexpressed: list[str] | None = None) -> LeadDeps:
    state = pipeline_state("plasmodb", user_prompt=_ADDED)
    state.domain.original_request = _ASKED
    state.domain.request_messages = [_ASKED]
    state.domain.requirements = [
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum 3D7")
    ]
    state.domain.operational_spec = OperationalSpec(
        goal=_ASKED,
        criteria=[
            Criterion(
                id="s1",
                text="genes with a signal peptide",
                search_name="GenesWithSignalPeptide",
                unexpressed_qualifiers=list(unexpressed or []),
            )
        ],
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=_STRATEGY,
        root_count=5,
        node_results=[
            NodeResult(
                node_id="s1",
                search_name="GenesWithSignalPeptide",
                wdk_step_id=_ROOT,
                count=5,
                status="ok",
            )
        ],
    )
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Signal peptides", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id="s1", search_name="GenesWithSignalPeptide")
    )
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"s1": _ROOT},
        step_counts={"s1": 5},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=_ROOT),
    )
    return lead_deps(state, strategy_session=session)


def test_the_scope_numbers_every_message_of_the_request() -> None:
    scope = verification_scope(_deps(), check_id="call_verify")

    assert scope.messages == [_ASKED, _ADDED]
    assert scope.stated == [
        (
            "organism (organism): 'Plasmodium falciparum 3D7' -> grounded "
            "(from an earlier message)"
        )
    ]


def test_the_scope_lists_each_word_no_search_states() -> None:
    scope = verification_scope(_deps(unexpressed=["exported"]), check_id="call_v")

    assert scope.unexpressed == ["'exported' in [s1] genes with a signal peptide"]


def test_the_work_order_names_the_root_to_sample() -> None:
    root = RootSample(step_id="s1", wdk_step_id=_ROOT, count=5)

    assert work_order("check it", None, root) == (
        "Verification work order: check it\n"
        "Inspect the built strategy. Return a VerificationDelta.\n"
        f"The root is s1, step {_ROOT} on the site, 5 records. Sample it with "
        f"get_sample_records(wdk_step_id={_ROOT}, limit=5)."
    )


def test_an_empty_root_is_not_sampled() -> None:
    order = work_order(
        "check it", None, RootSample(step_id="s1", wdk_step_id=_ROOT, count=0)
    )

    assert order.endswith(
        f"The root is s1, step {_ROOT} on the site, 0 records. "
        "It holds no gene to sample."
    )


def test_a_root_larger_than_the_sample_is_read_eight_records_deep() -> None:
    order = work_order(
        "check it", None, RootSample(step_id="s1", wdk_step_id=_ROOT, count=212)
    )

    assert order.endswith(f"get_sample_records(wdk_step_id={_ROOT}, limit=8).")


def _digest(review: dict[str, Any]) -> VerificationDelta:
    return VerificationDelta.model_validate(
        {
            "digest": {
                "disposition": "done",
                "prose": "The strategy returns 5 genes.",
                "reason": "Counts and records read.",
                "success": True,
                "review": review,
            }
        }
    )


class _Dispatch:
    """Stands in for the VERIFY run and the site's count read."""

    def __init__(self, outcome: VerificationDelta) -> None:
        self.outcome = outcome
        self.agent_deps: AgentDeps | None = None
        self.work_order = ""

    async def streamed(self, **kwargs: Any) -> VerificationDelta:
        self.agent_deps = kwargs["agent_deps"]
        self.work_order = kwargs["run"].work_order
        return self.outcome


async def _run(
    monkeypatch: pytest.MonkeyPatch, deps: LeadDeps, review: dict[str, Any]
) -> tuple[VerificationDelta, _Dispatch]:
    dispatch = _Dispatch(_digest(review))

    async def counts(site_id: str, wdk_strategy_id: int) -> SiteCounts:
        del site_id, wdk_strategy_id
        return SiteCounts(root_step_id=_ROOT, counts={_ROOT: 5})

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", dispatch.streamed)
    monkeypatch.setattr(evidence_card, "read_step_counts", counts)
    delta = await run_verification(
        deps=deps, parent_tool_call_id="call_verify", reason="check the genes"
    )
    assert isinstance(delta, VerificationDelta)
    return delta, dispatch


_UNMET = {
    "text": "at least 2 transmembrane domains",
    "turn": 2,
    "answeredBy": [],
    "how": "search",
    "status": "unmet",
    "note": "no step reads transmembrane domains",
}


async def test_an_unmet_requirement_refuses_the_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta, _dispatch = await _run(monkeypatch, _deps(), {"requirements": [_UNMET]})

    assert delta.digest.success is False
    assert delta.digest.reason == (
        "Verification reported success, but the check reports 1 requirement "
        "unmet: 'at least 2 transmembrane domains'."
    )


def _gene(gene_id: str, fits: str) -> dict[str, str]:
    return {
        "geneId": gene_id,
        "product": "erythrocyte membrane protein",
        "organism": "Plasmodium falciparum 3D7",
        "fits": fits,
        "why": "the product names a membrane protein",
    }


async def test_genes_that_do_not_fit_are_counted_in_the_caveats(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    deps = _deps()
    for gene_id in ("PF3D7_0100100", "PF3D7_0100200"):
        deps.state.turn_markers.record_retrieved_source(_RECORD.format(gene_id))

    delta, _dispatch = await _run(
        monkeypatch,
        deps,
        {
            "sampledGenes": [
                _gene("PF3D7_0100100", "yes"),
                _gene("PF3D7_0100200", "no"),
                _gene("PF3D7_0100300", "yes"),
            ]
        },
    )

    assert delta.digest.caveats == [
        (
            "1 of 2 sampled genes do not fit: `PF3D7_0100200` (the product names a "
            "membrane protein)"
        )
    ]
    card = deps.state.domain.last_evidence_card
    assert card is not None
    assert [gene.gene_id for gene in card.review.sampled_genes] == [
        "PF3D7_0100100",
        "PF3D7_0100200",
    ]
    assert (
        collector.data_of("data-evidence-card")[0]["review"]["sampledGenes"][1]["fits"]
        == "no"
    )


async def test_the_check_reads_at_most_eight_gene_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _delta, dispatch = await _run(monkeypatch, _deps(), {})

    assert dispatch.agent_deps is not None
    guard: ToolRepetitionGuard = dispatch.agent_deps.tool_repetition_guard
    allowed = [
        guard.check("read_gene_record", {"gene_id": f"PF3D7_{i:07d}"})
        for i in range(SAMPLED_GENE_LIMIT)
    ]
    refused = guard.check("read_gene_record", {"gene_id": "PF3D7_0000009"})

    assert allowed == [None] * SAMPLED_GENE_LIMIT
    assert refused is not None
    assert refused.rule == "call_cap"
    assert dispatch.work_order.endswith(
        f"get_sample_records(wdk_step_id={_ROOT}, limit=5)."
    )
