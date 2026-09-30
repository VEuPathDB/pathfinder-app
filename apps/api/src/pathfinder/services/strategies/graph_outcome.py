"""The BuildOutcome that describes the strategy a commit left behind."""

from __future__ import annotations

from collections.abc import Collection

from veupathdb.domain.strategy import rebuild_tree, wdk_search_name

from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    StepPushFailure,
    built_counts,
)
from pathfinder.domain.strategy.orthology import organism_change
from pathfinder.domain.strategy.session import (
    StrategyGraph,
    StrategySession,
    strategy_root_id,
)
from pathfinder.services.strategies.spec_build import node_results
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state

__all__ = ["live_outcome", "outcome_for_graph"]


def outcome_for_graph(
    *,
    graph: StrategyGraph | None,
    sync_state: WDKSyncState,
    failed_step_ids: Collection[str],
) -> BuildOutcome:
    """The build the graph now holds. The organisms are read on the parameters
    the last sync found marked."""
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
        zero_step_ids=built_counts(graph, sync_state).zero_step_ids,
        organism_change=(
            organism_change(
                rebuild_tree(root_id, graph.steps), sync_state.organism_params
            )
            if graph is not None and root_id is not None
            else None
        ),
    )
    outcome.node_results = node_results(steps, sync_state, outcome)
    return outcome


def live_outcome(
    session: StrategySession, failed_step_ids: Collection[str] | None = None
) -> BuildOutcome:
    """The build the session's strategy holds now.

    ``failed_step_ids`` None names every step the sync state records as refused.
    """
    sync_state = ensure_sync_state(session)
    return outcome_for_graph(
        graph=session.get_graph(None),
        sync_state=sync_state,
        failed_step_ids=(
            sync_state.wdk_push_errors.keys()
            if failed_step_ids is None
            else failed_step_ids
        ),
    )
