from __future__ import annotations

from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    built_counts,
    node_status,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies.sync_state import WDKSyncState


def test_node_status_classifier() -> None:
    assert node_status(count=437, failed=False) == "ok"
    assert node_status(count=0, failed=False) == "zero"
    assert node_status(count=None, failed=True) == "failed"
    assert node_status(count=None, failed=False) == "ok"


def test_node_result_serializes_camelcase() -> None:
    nr = NodeResult(
        node_id="s1",
        search_name="GenesWithSignalPeptide",
        wdk_step_id=123,
        status="ok",
    )
    dumped = nr.model_dump(by_alias=True)
    assert dumped["searchName"] == "GenesWithSignalPeptide"
    assert dumped["wdkStepId"] == 123
    assert dumped["status"] == "ok"


def test_build_outcome_carries_node_results() -> None:
    outcome = BuildOutcome(
        node_results=[NodeResult(node_id="s1", search_name="S", status="zero")]
    )
    assert [(n.node_id, n.status) for n in outcome.node_results] == [("s1", "zero")]


def _synced(counts: dict[str, int | None], refused: dict[str, str]) -> WDKSyncState:
    return WDKSyncState(
        wdk_step_ids={step_id: 900 + i for i, step_id in enumerate(counts)},
        step_counts=counts,
        wdk_push_errors=refused,
    )


def test_the_counts_are_the_sync_states_and_a_refused_step_has_none() -> None:
    graph = StrategyGraph("g1", "Test", "plasmodb")
    graph.roots = {"root"}
    counts = built_counts(
        graph, _synced({"leaf": 0, "refused": 12, "root": 440}, {"refused": "400"})
    )

    assert (
        dict(counts.by_step),
        counts.root_count,
        counts.zero_step_ids,
        counts.of("absent"),
    ) == ({"leaf": 0, "refused": None, "root": 440}, 440, ["leaf"], None)


def test_a_session_with_no_sync_state_holds_no_count() -> None:
    counts = built_counts(StrategyGraph("g1", "Test", "plasmodb"), None)

    assert (dict(counts.by_step), counts.root_count) == ({}, None)
