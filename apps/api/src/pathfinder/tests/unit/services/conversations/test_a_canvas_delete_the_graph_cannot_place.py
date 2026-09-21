"""The graph route answers a delete the algebra cannot perform."""

from __future__ import annotations

import pytest
from veupathdb.errors import ValidationError

from pathfinder.domain.strategy.operations import (
    DeleteResolution,
    DeleteStepOp,
    UpdateStepMetaOp,
)
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.services.conversations.strategy_ops import (
    refuse_a_delete_the_graph_cannot_place,
)
from pathfinder.tests.unit.domain.strategy._builders import (
    combine,
    graph_with,
    leaf,
    transform,
)


def test_a_promote_of_a_leaf_is_refused() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])
    op = DeleteStepOp(step_id="a", resolution=DeleteResolution.PROMOTE_PRIMARY)

    with pytest.raises(ValidationError, match="reads no step that can take its place"):
        refuse_a_delete_the_graph_cannot_place(graph, op)


def test_an_orphan_sibling_on_a_root_is_refused() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])
    op = DeleteStepOp(step_id="c", resolution=DeleteResolution.ORPHAN_SIBLING)

    with pytest.raises(ValidationError, match="is a root"):
        refuse_a_delete_the_graph_cannot_place(graph, op)


def test_a_step_the_strategy_does_not_hold_is_refused() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])
    op = DeleteStepOp(step_id="gone", resolution=DeleteResolution.DELETE_SUBTREE)

    with pytest.raises(ValidationError, match="is not a step of this strategy"):
        refuse_a_delete_the_graph_cannot_place(graph, op)


def test_a_delete_of_a_root_transform_is_allowed() -> None:
    """The step the transform consumed takes its place, so the delete stands."""
    graph = graph_with([transform("t", combine("c", leaf("a"), leaf("b")))])
    op = DeleteStepOp(step_id="t", resolution=DeleteResolution.COLLAPSE_COMBINE)

    refuse_a_delete_the_graph_cannot_place(graph, op)
    apply_operation(graph, op)

    assert sorted(graph.steps) == ["a", "b", "c"]


def test_an_operation_that_deletes_nothing_is_not_read() -> None:
    graph = graph_with([leaf("a")])
    op = UpdateStepMetaOp(step_id="a", display_name="renamed")

    refuse_a_delete_the_graph_cannot_place(graph, op)
    apply_operation(graph, op)

    assert graph.steps["a"].display_name == "renamed"


def test_a_thread_with_no_graph_is_left_to_the_commit() -> None:
    """A thread holding no graph is answered by the commit, not by the route."""
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])
    op = DeleteStepOp(step_id="a", resolution=DeleteResolution.PROMOTE_PRIMARY)

    refuse_a_delete_the_graph_cannot_place(None, op)

    with pytest.raises(ValidationError):
        refuse_a_delete_the_graph_cannot_place(graph, op)
