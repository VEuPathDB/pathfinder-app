"""Pushing a step to WDK invalidates its cached count, and its ancestors'.

A parameter edit changes what the step returns, so the stored count is wrong
the instant the push succeeds, and every combine that reads that step answers
over the new result. ``None`` means "unknown, go recompute" - every consumer
already handles it. A stale integer reads as fact.
"""

from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree

from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.services.strategies.wdk_counts import invalidate_counts_for


def _graph() -> StrategyGraph:
    """``c`` unions the two leaves ``a`` and ``b``."""
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
    root = StrategyStepNode(
        id="c",
        search_name="__combine__",
        primary_input=StrategyStepNode(id="a", search_name="GenesByText"),
        secondary_input=StrategyStepNode(id="b", search_name="GenesByText"),
        operator=CombineOp.UNION,
    )
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    return graph


def _state() -> WDKSyncState:
    state = WDKSyncState()
    state.step_counts = {"a": 2862, "b": 100, "c": 2900}
    return state


def test_pushed_step_count_becomes_unknown() -> None:
    state = _state()
    invalidate_counts_for(state, ["a"], graph=_graph())
    assert state.step_counts["a"] is None


def test_the_combine_above_it_becomes_unknown_and_the_sibling_stands() -> None:
    state = _state()
    invalidate_counts_for(state, ["a"], graph=_graph())
    assert state.step_counts == {"a": None, "b": 100, "c": None}


def test_invalidating_many_steps() -> None:
    state = _state()
    invalidate_counts_for(state, ["a", "b"], graph=_graph())
    assert state.step_counts == {"a": None, "b": None, "c": None}


def test_empty_push_changes_nothing() -> None:
    state = _state()
    invalidate_counts_for(state, [], graph=_graph())
    assert state.step_counts == {"a": 2862, "b": 100, "c": 2900}


def test_unknown_step_id_is_ignored() -> None:
    # A step that was never counted must not gain a phantom entry.
    state = _state()
    invalidate_counts_for(state, ["never-seen"], graph=_graph())
    assert "never-seen" not in state.step_counts
