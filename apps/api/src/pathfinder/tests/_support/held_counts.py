"""A session whose sync state holds the count of one built step."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState


def hold_one_step(
    session: StrategySession, step_id: str, search_name: str, count: int | None
) -> StrategySession:
    """Put a strategy of one step that reached the site with ``count`` records
    into ``session``, and hand the session back."""
    graph = StrategyGraph(graph_id="g1", name="Built", site_id=session.site_id)
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id=step_id, search_name=search_name))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={step_id: 900_001},
        step_counts={step_id: count},
        wdk_strategy_id=330_423_363,
    )
    return session


def session_holding(
    site_id: str, step_id: str, search_name: str, count: int | None
) -> StrategySession:
    """A session of one step that reached the site with ``count`` records."""
    return hold_one_step(StrategySession(site_id=site_id), step_id, search_name, count)
