"""VERIFY is handed every message of the request, the checks the runtime ran
and the root it may sample, and its sampled genes reach the card as the record
lets them stand."""

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
from pathfinder.ai.lead.verification_scope import verification_scope
from pathfinder.ai.lead.verify_dispatch import (
    RootSample,
    run_verification,
    work_order,
)
from pathfinder.domain.caveats import SampleCaveat
from pathfinder.domain.evidence import SAMPLED_GENE_LIMIT
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.site_counts import SiteCounts
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.column_fits import tm_fit
from pathfinder.tests._support.site_checks import PASSED, checked_site
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
_RECORD = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/{}"

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
        node_results=[
            NodeResult(
                node_id="s1",
                search_name="GenesWithSignalPeptide",
                wdk_step_id=_ROOT,
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


def test_the_work_order_names_the_checks_then_the_root_to_sample() -> None:
    root = RootSample(step_id="s3", wdk_step_id=_ROOT, count=5)

    assert work_order("check it", None, root, [PASSED], [tm_fit(5, 5)]) == (
        "Verification work order: check it\n"
        "Inspect the built strategy. Return a VerificationDelta.\n"
        "The runtime read the strategy on the site. These checks decide the "
        "verdict:\n"
        "- [pass] the strategy on the site: the result holds records on the site\n"
        "- [column] 5 of 5 transcripts fit # TM Domains (2 to 99)\n"
        f"The root is s3, step {_ROOT} on the site, 5 records. To say what its "
        "records look like, sample it with "
        f"get_sample_records(wdk_step_id={_ROOT}, limit=5)."
    )


def test_the_work_order_names_each_step_no_column_shows() -> None:
    note = (
        "No column of GenesByText shows a numeric value its criterion binds. "
        "Sample the root with get_sample_records for this criterion."
    )

    order = work_order("check it", None, None, [], [], [note])

    assert order.splitlines()[-1] == f"- [no column] {note}"


def test_the_dispatch_names_the_strategys_root() -> None:
    assert verify_dispatch.root_sample(_deps()) == RootSample(
        step_id="s1", wdk_step_id=_ROOT, count=5
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
        {"digest": {"prose": "The strategy returns 5 genes.", "review": review}}
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

    checked_site(monkeypatch)
    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", dispatch.streamed)
    monkeypatch.setattr(evidence_card, "read_step_counts", counts)
    delta = await run_verification(
        deps=deps, parent_tool_call_id="call_verify", reason="check the genes"
    )
    assert isinstance(delta, VerificationDelta)
    return delta, dispatch


def _gene(gene_id: str, fits: str) -> dict[str, str]:
    return {
        "geneId": gene_id,
        "product": "erythrocyte membrane protein",
        "organism": "Plasmodium falciparum 3D7",
        "fits": fits,
        "why": "the product names a membrane protein",
    }


async def test_the_columns_this_turn_read_are_the_cards_and_the_caveats(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    deps = _deps()
    short = tm_fit(3, 5, wdk_step_id=_ROOT)
    deps.state.turn_markers.record_column_fits(
        [short, tm_fit(9, 9, wdk_step_id=_ROOT + 1)]
    )
    for gene_id in ("PF3D7_0100100", "PF3D7_0100200"):
        deps.state.turn_markers.record_retrieved_source(_RECORD.format(gene_id))

    delta, _dispatch = await _run(
        monkeypatch,
        deps,
        {
            "sampledGenes": [
                _gene("PF3D7_0100100", "yes"),
                _gene("PF3D7_0100200", "no"),
            ]
        },
    )

    assert delta.digest.caveats == [SampleCaveat(fit=short)]
    card = deps.state.domain.last_evidence_card
    assert card is not None
    assert (
        card.review.column_fits,
        [gene.gene_id for gene in card.review.sampled_genes],
    ) == ([short], ["PF3D7_0100100", "PF3D7_0100200"])
    streamed = collector.data_of("data-evidence-card")[0]["review"]
    assert (streamed["columnFits"][0]["fits"], streamed["sampledGenes"][1]["fits"]) == (
        "some",
        "no",
    )


async def test_the_checks_guard_leaves_record_reads_to_the_reading_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _delta, dispatch = await _run(monkeypatch, _deps(), {})

    assert dispatch.agent_deps is not None
    guard: ToolRepetitionGuard = dispatch.agent_deps.tool_repetition_guard
    reads = [
        guard.check("read_gene_record", {"gene_id": f"PF3D7_{i:07d}"}, run_step=i + 1)
        for i in range(SAMPLED_GENE_LIMIT + 1)
    ]

    assert reads == [None] * (SAMPLED_GENE_LIMIT + 1)
    assert dispatch.work_order.endswith(
        f"get_sample_records(wdk_step_id={_ROOT}, limit=5)."
    )
