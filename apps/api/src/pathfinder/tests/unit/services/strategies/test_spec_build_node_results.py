from __future__ import annotations

from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    StepPushFailure,
    built_counts,
)
from pathfinder.services.strategies.spec_build import node_results
from pathfinder.services.strategies.sync_state import WDKSyncState


def _leaf(step_id: str, search_name: str) -> StrategyStep:
    return StrategyStep(id=step_id, kind=StepKind.SEARCH, search_name=search_name)


def test_node_results_read_their_status_at_the_sync_states_counts() -> None:
    leaf1 = _leaf("s1", "GenesWithSignalPeptide")
    leaf2 = _leaf("s2", "GenesByTransmembraneDomains")
    sync = WDKSyncState()
    sync.wdk_step_ids = {leaf1.id: 100, leaf2.id: 200}
    sync.step_counts = {leaf1.id: 437, leaf2.id: 0}
    outcome = BuildOutcome()

    results = {r.node_id: r for r in node_results([leaf1, leaf2], sync, outcome)}

    assert results[leaf1.id].status == "ok"
    assert results[leaf1.id].wdk_step_id == 100
    assert results[leaf1.id].search_name == "GenesWithSignalPeptide"
    assert results[leaf2.id].status == "zero"


def test_node_results_mark_a_failed_node_with_its_error() -> None:
    leaf = _leaf("s1", "GenesByTransmembraneDomains")
    outcome = BuildOutcome(
        failed_steps=[
            StepPushFailure(
                step_id=leaf.id,
                search_name="GenesByTransmembraneDomains",
                error="bad param",
            )
        ]
    )

    results = node_results([leaf], WDKSyncState(), outcome)

    assert results[0].status == "failed"
    assert results[0].error == "bad param"


def test_a_failed_node_reports_no_count_even_when_one_was_measured() -> None:
    """The measured count is the search WDK still runs, not the one the node states."""
    leaf = _leaf("step_7c2e770b", "GenesByMicroarrayBirkholtz")
    sync = WDKSyncState()
    sync.wdk_step_ids = {leaf.id: 440432473}
    sync.step_counts = {leaf.id: 1282}
    sync.wdk_push_errors = {leaf.id: "422 profileset_generic: Invalid value"}
    outcome = BuildOutcome(
        failed_steps=[
            StepPushFailure(
                step_id=leaf.id,
                search_name="GenesByMicroarrayBirkholtz",
                error="422 profileset_generic: Invalid value",
                wdk_status=422,
            )
        ],
    )

    results = node_results([leaf], sync, outcome)

    assert (results[0].status, built_counts(None, sync).of(leaf.id)) == (
        "failed",
        None,
    )
