"""Shared builder helpers for test data construction."""

from veupathdb.domain.strategy.graph_model import StrategyStep

from pathfinder.domain.strategy.session import StrategyGraph


def add_step_to_graph(graph: StrategyGraph, step: StrategyStep) -> None:
    """Put one step into a graph the way a hydration does.

    Insertion order decides a tie between two roots, so a case adds its steps
    in the order it describes.
    """
    graph.steps[step.id] = step
    graph.recompute_roots()
    graph.last_step_id = step.id
