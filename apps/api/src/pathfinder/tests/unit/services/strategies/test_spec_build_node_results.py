from __future__ import annotations

from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from pathfinder.services.strategies.spec_build import node_results
from pathfinder.services.strategies.sync_state import WDKSyncState


def _leaf(step_id: str, search_name: str) -> StrategyStep:
    return StrategyStep(id=step_id, kind=StepKind.SEARCH, search_name=search_name)


def testnode_results_maps_counts_and_step_ids() -> None:
    leaf1 = _leaf("s1", "GenesWithSignalPeptide")
    leaf2 = _leaf("s2", "GenesByTransmembraneDomains")
    sync = WDKSyncState()
    sync.wdk_step_ids = {leaf1.id: 100, leaf2.id: 200}
    outcome = BuildOutcome(counts={leaf1.id: 437, leaf2.id: 0})

    results = {r.node_id: r for r in node_results([leaf1, leaf2], sync, outcome)}

    assert results[leaf1.id].status == "ok"
    assert results[leaf1.id].count == 437
    assert results[leaf1.id].wdk_step_id == 100
    assert results[leaf1.id].search_name == "GenesWithSignalPeptide"
    assert results[leaf2.id].status == "zero"


def testnode_results_marks_failed_with_error() -> None:
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
    assert results[0].count is None


def test_a_failed_node_reports_no_count_even_when_one_was_measured() -> None:
    """The measured count is the search WDK still runs, not the one the node states."""
    leaf = _leaf("step_7c2e770b", "GenesByMicroarrayBirkholtz")
    sync = WDKSyncState()
    sync.wdk_step_ids = {leaf.id: 440432473}
    outcome = BuildOutcome(
        counts={leaf.id: 1282},
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

    assert results[0].status == "failed"
    assert results[0].count is None
