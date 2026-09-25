"""The searches a thread's strategy already runs, as a separation's candidates."""

from __future__ import annotations

from veupathdb_mcp.separation import ThreadSearch

from pathfinder.domain.strategy.session import StrategyGraph


def thread_searches(graph: StrategyGraph | None) -> list[ThreadSearch]:
    """Each leaf of the thread's strategy, with the parameters its step runs.

    A step that takes an input is not a leaf, so it is not a candidate.
    """
    if graph is None:
        return []
    return [
        ThreadSearch(search_name=step.search_name, parameters=dict(step.parameters))
        for step in graph.steps.values()
        if step.search_name and not step.input_ids()
    ]
