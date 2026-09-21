"""What the delete menu owes the apply, over arbitrary trees.

Every resolution ``compute_delete_choices`` offers for a step is applied to a
copy of the graph. The apply performs it, the steps it names are the steps it
removes, and what is left is one tree with nothing unreachable in it.
"""

from __future__ import annotations

from hypothesis import given, settings
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.operations.resolutions import compute_delete_choices
from pathfinder.domain.strategy.operations.types import DeleteStepOp
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.tests.unit.domain.strategy._builders import (
    combine,
    graph_of,
    leaf,
    strategy_trees,
    transform,
)

PROFILE = settings(max_examples=60, deadline=None)


def _reachable(graph: StrategyGraph) -> set[str]:
    root = graph.primary_root_id()
    if root is None:
        return set()
    seen: set[str] = set()
    stack = [root]
    while stack:
        step_id = stack.pop()
        if step_id in seen:
            continue
        seen.add(step_id)
        stack.extend(graph.steps[step_id].input_ids())
    return seen


def _nothing_is_stranded(graph: StrategyGraph) -> None:
    """Every step that is left answers to the one root that is left."""
    if not graph.steps:
        return
    assert len(graph.roots) == 1
    assert _reachable(graph) == set(graph.steps)


def _steps_the_menu_placed(root: StrategyStepNode) -> list[str]:
    """Every step whose offered deletes the graph performed, id order."""
    before = graph_of(root)
    placed: list[str] = []
    for step_id in sorted(before.steps):
        for choice in compute_delete_choices(before, step_id):
            graph = graph_of(root)
            op = DeleteStepOp(step_id=step_id, resolution=choice.resolution)
            result = apply_operation(graph, op)
            assert sorted(result.dropped_step_ids) == sorted(choice.will_delete), (
                f"{step_id} {choice.resolution}"
            )
            assert set(graph.steps) == set(before.steps) - set(choice.will_delete)
            _nothing_is_stranded(graph)
        placed.append(step_id)
    return placed


@PROFILE
@given(root=strategy_trees())
def test_every_choice_offered_for_every_step_is_performed(
    root: StrategyStepNode,
) -> None:
    assert _steps_the_menu_placed(root) == sorted(graph_of(root).steps)


def test_a_root_transform_offers_the_delete_that_keeps_its_input() -> None:
    """The transform goes and the branch it read becomes the strategy's root."""
    root = transform("t0", combine("c0", leaf("a"), leaf("b")))

    assert _steps_the_menu_placed(root) == ["a", "b", "c0", "t0"]
