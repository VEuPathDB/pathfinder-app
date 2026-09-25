"""The BuildOutcome that describes the strategy a commit left behind."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from veupathdb.domain.strategy import rebuild_tree, wdk_search_name

from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    StepPushFailure,
    citable_count,
)
from pathfinder.domain.strategy.orthology import organism_change
from pathfinder.domain.strategy.session import StrategyGraph, strategy_root_id
from pathfinder.services.strategies.spec_build import node_results
from pathfinder.services.strategies.sync_state import WDKSyncState

__all__ = ["outcome_for_graph"]


def outcome_for_graph(
    *,
    graph: StrategyGraph | None,
    sync_state: WDKSyncState,
    counts: Mapping[str, int | None],
    failed_step_ids: Collection[str],
    wdk_url: str | None,
) -> BuildOutcome:
    """The build the graph now holds, with the counts the caller measured.

    A count the caller does not carry is unknown, so the step reports no
    number rather than one from an earlier build.
    """
    steps = list(graph.steps.values()) if graph is not None else []
    root_id = strategy_root_id(graph, sync_state) if graph is not None else None
    outcome = BuildOutcome(
        pushed_step_ids=[s.id for s in steps if s.id in sync_state.wdk_step_ids],
        failed_steps=[
            StepPushFailure(
                step_id=step.id,
                search_name=wdk_search_name(step),
                error=sync_state.wdk_push_errors.get(step.id, ""),
            )
            for step in steps
            if step.id in failed_step_ids
        ],
        wdk_strategy_id=sync_state.wdk_strategy_id,
        wdk_url=wdk_url,
        counts=dict(counts),
        root_count=(
            citable_count(root_id, counts=counts, refused=sync_state.wdk_push_errors)
            if root_id is not None
            else None
        ),
        zero_step_ids=[sid for sid, count in counts.items() if count == 0],
        organism_change=(
            organism_change(rebuild_tree(root_id, graph.steps))
            if graph is not None and root_id is not None
            else None
        ),
    )
    outcome.node_results = node_results(steps, sync_state, outcome)
    return outcome
