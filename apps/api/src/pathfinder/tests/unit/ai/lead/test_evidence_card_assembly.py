"""Every value on the evidence card equals the record it was read from."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from assistant_core.graph.turn_state import SubAgentApprovalPending
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead import evidence_card, verify_dispatch
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.evidence_card import CardSources, assemble_evidence_card
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    CriterionCitations,
    EvidenceVerdict,
    VerificationReview,
)
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.services.strategies.site_counts import SiteCounts
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
)

_STRATEGY = 300125410
_LEAF = 440299573
_CHECKED_AT = datetime(2026, 9, 24, 9, 30, tzinfo=UTC)
_POSITIVE = ControlSetEvidence(
    returned=[f"PF3D7_{index:07d}" for index in range(7)],
    not_returned=["PF3D7_0000007", "PF3D7_0000008", "PF3D7_0000009"],
)
_NEGATIVE = ControlSetEvidence(
    returned=["PF3D7_1000000"],
    not_returned=[f"PF3D7_{index:07d}" for index in range(1000001, 1000012)],
)
_PAPER = "https://doi.org/10.1038/nature12970"


def _test_run(
    wdk_step_id: int | None, *, call: str = "call_controls"
) -> ControlTestRun:
    return ControlTestRun(
        tool_call_id=call,
        evidence=ControlTestEvidence(
            tested_label="Kinases",
            wdk_step_id=wdk_step_id,
            positive=_POSITIVE,
            negative=_NEGATIVE,
        ),
    )


def _spec() -> OperationalSpec:
    rationale = SearchRationale(
        search_name="GenesByText",
        basis="parameter",
        term="Text term",
        reason="The request names kinases by their product description.",
        tool_call_id="call_search",
        sources=[_PAPER],
    )
    return OperationalSpec(
        goal="kinases",
        criteria=[
            Criterion(id="c1", text="protein kinases", rationale=rationale),
            Criterion(id="c2", text="exported proteins"),
        ],
    )


_BASE = CardSources(
    check_id="call_verify",
    revision="rev-1",
    site_id="plasmodb",
    labels={"s1": "Kinases"},
    live_wdk_step_ids=frozenset({_LEAF}),
    wdk_strategy_id=_STRATEGY,
    root_wdk_step_id=_LEAF,
    node_results=(
        NodeResult(
            node_id="s1",
            search_name="GenesByText",
            wdk_step_id=_LEAF,
            count=212,
            status="ok",
        ),
        NodeResult(
            node_id="gone",
            search_name="GenesWithSignalPeptide",
            wdk_step_id=440299001,
            count=1143,
            status="ok",
        ),
    ),
    spec=_spec(),
    control_tests=(_test_run(_LEAF), _test_run(440299001, call="call_old")),
    verdict=EvidenceVerdict(supported=True),
    review=VerificationReview(),
)


def _sources(**changes: Any) -> CardSources:
    return replace(_BASE, **changes)


def test_every_field_equals_its_source() -> None:
    card = assemble_evidence_card(
        _sources(),
        SiteCounts(root_step_id=_LEAF, counts={_LEAF: 230}),
        checked_at=_CHECKED_AT,
    )

    assert card.strategy_url == (
        "https://plasmodb.org/plasmo/app/workspace/strategies/300125410/440299573"
    )
    assert card.site_read == "read"
    assert [
        (s.step_id, s.title, s.recorded_count, s.site_count, s.drifted)
        for s in card.steps
    ] == [("s1", "Kinases", 212, 230, True)]
    assert [test.wdk_step_id for test in card.controls] == [_LEAF]
    tested = card.controls[0]
    assert tested.positive == _POSITIVE
    assert tested.negative == _NEGATIVE
    assert tested.enrichment is not None
    assert (
        tested.enrichment.population,
        tested.enrichment.positives,
        tested.enrichment.returned,
        tested.enrichment.positives_returned,
    ) == (22, 10, 8, 7)
    assert tested.enrichment.p_value == pytest.approx(1485 / 319770)
    assert card.citations == [
        CriterionCitations(
            criterion_id="c1", criterion_text="protein kinases", references=[_PAPER]
        )
    ]
    assert card.verdict == EvidenceVerdict(supported=True)


def test_a_site_that_did_not_answer_leaves_every_site_count_empty() -> None:
    card = assemble_evidence_card(_sources(), None, checked_at=_CHECKED_AT)

    assert card.site_read == "not_answered"
    assert [step.site_count for step in card.steps] == [None]
    assert card.strategy_url == (
        "https://plasmodb.org/plasmo/app/workspace/strategies/300125410/440299573"
    )


def test_the_card_shows_control_tests_and_no_comparison_or_sweep() -> None:
    """A comparison variant or a sweep setting backs a claim; it is no check."""
    tested = _test_run(_LEAF)
    sweep = ControlTestRun(
        tool_call_id="call_sweep:v0",
        origin="sweep",
        evidence=tested.evidence.model_copy(update={"tested_label": "setting v0"}),
    )
    scored = ControlTestRun(
        tool_call_id="call_compare:B",
        origin="scored_comparison",
        evidence=tested.evidence.model_copy(
            update={"tested_label": "B", "wdk_step_id": None}
        ),
    )

    card = assemble_evidence_card(
        _sources(control_tests=(tested, sweep, scored)), None, checked_at=_CHECKED_AT
    )

    assert [test.tested_label for test in card.controls] == ["Kinases"]


def test_a_search_level_test_stays_on_the_card() -> None:
    card = assemble_evidence_card(
        _sources(control_tests=(_test_run(None),)), None, checked_at=_CHECKED_AT
    )

    assert [test.wdk_step_id for test in card.controls] == [None]


def test_a_strategy_not_on_the_site_has_no_link() -> None:
    card = assemble_evidence_card(
        _sources(wdk_strategy_id=None), None, checked_at=_CHECKED_AT
    )

    assert (card.wdk_strategy_id, card.strategy_url) == (None, None)


_DIGEST = VerificationDelta.model_validate(
    {
        "digest": {
            "disposition": "done",
            "prose": "The strategy returns 212 kinases.",
            "reason": "Counts read from the strategy.",
            "success": True,
        }
    }
)


def _checked_deps() -> LeadDeps:
    state = pipeline_state("plasmodb", user_prompt="Find kinases in P. falciparum.")
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=_STRATEGY,
        node_results=[
            NodeResult(
                node_id="s1",
                search_name="GenesByText",
                wdk_step_id=_LEAF,
                count=212,
                status="ok",
            )
        ],
    )
    state.turn_markers.record_control_tests([_test_run(_LEAF)])
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id="s1", search_name="GenesByText", display_name="Kinases")
    )
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"s1": _LEAF}, step_counts={"s1": 212}, wdk_strategy_id=_STRATEGY
    )
    return lead_deps(state, strategy_session=session)


async def _dispatch(
    monkeypatch: pytest.MonkeyPatch,
    deps: LeadDeps,
    outcome: VerificationDelta | SubAgentApprovalWait,
) -> VerificationDelta | SubAgentApprovalWait:
    async def streamed(**_kwargs: object) -> VerificationDelta | SubAgentApprovalWait:
        return outcome

    async def counts(site_id: str, wdk_strategy_id: int) -> SiteCounts:
        del site_id, wdk_strategy_id
        return SiteCounts(root_step_id=_LEAF, counts={_LEAF: 212})

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", streamed)
    monkeypatch.setattr(evidence_card, "read_step_counts", counts)
    return await run_verification(
        deps=deps, parent_tool_call_id="call_verify", reason="check the kinases"
    )


async def test_a_finished_check_emits_one_card(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    deps = _checked_deps()

    await _dispatch(monkeypatch, deps, _DIGEST)

    emitted = collector.data_of("data-evidence-card")
    card = deps.state.domain.last_evidence_card
    assert card is not None
    assert emitted == [card.model_dump(by_alias=True, mode="json")]
    assert card.check_id == "call_verify"
    assert [(s.recorded_count, s.site_count) for s in card.steps] == [(212, 212)]


async def test_a_parked_check_emits_no_card(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    deps = _checked_deps()
    parked = SubAgentApprovalWait(
        pending=SubAgentApprovalPending(
            role="verification", approvals=[], messages_json="[]"
        )
    )

    await _dispatch(monkeypatch, deps, parked)

    assert collector.data_of("data-evidence-card") == []
    assert deps.state.domain.last_evidence_card is None


_FAILED_DIGEST = VerificationDelta.model_validate(
    {
        "digest": {
            "disposition": "done",
            "prose": "The strategy returns no genes.",
            "reason": "The root step returned 0 genes.",
            "success": False,
        }
    }
)


@pytest.mark.parametrize("digest", [_DIGEST, _FAILED_DIGEST])
async def test_a_failed_verdict_names_the_build_whichever_side_found_it(
    monkeypatch: pytest.MonkeyPatch,
    collector: ChunkCollector,
    digest: VerificationDelta,
) -> None:
    del collector
    deps = _checked_deps()
    built = deps.state.domain.last_build_outcome
    assert built is not None
    deps.state.domain.last_build_outcome = replace(built, zero_step_ids=["s1"])

    await _dispatch(monkeypatch, deps, digest)

    card = deps.state.domain.last_evidence_card
    assert card is not None
    assert (card.verdict.supported, card.verdict.refused_because) == (
        False,
        "the build pushed 1 step, failed 0, skipped 0 and left 1 empty",
    )
