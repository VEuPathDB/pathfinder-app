from __future__ import annotations

from veupathdb.domain.strategy.build_outcome import BuildOutcome, StepPushFailure
from veupathdb.domain.strategy.graph_model import StepKind, StrategyStep

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
