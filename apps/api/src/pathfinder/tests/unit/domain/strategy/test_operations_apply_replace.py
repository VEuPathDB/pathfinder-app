"""``replaceStrategy`` swaps the whole graph for the given tree.

Undo and redo on the canvas replay a cached strategy through this operation:
steps the tree does not mention are gone, and the tree's own root becomes the
graph's root.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp

from pathfinder.domain.strategy.operations import ReplaceStrategyOp
from pathfinder.domain.strategy.operations.apply import ApplyError, apply_operation

from ._builders import combine, graph_with, leaf


class TestReplaceStrategy:
    def test_the_operation_is_supported(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(graph, ReplaceStrategyOp(root=leaf("b")))

        assert sorted(graph.steps) == ["b"]

    def test_steps_absent_from_the_new_tree_are_dropped(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        apply_operation(graph, ReplaceStrategyOp(root=leaf("a")))

        assert sorted(graph.steps) == ["a"]

    def test_the_new_root_is_the_only_root(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(
            graph, ReplaceStrategyOp(root=combine("c", leaf("x"), leaf("y")))
        )

        assert graph.roots == {"c"}
        assert sorted(graph.steps) == ["c", "x", "y"]

    def test_structure_is_recorded_as_id_references(self) -> None:
        """Steps reference each other by id, so editing one cannot reach into
        another."""
        graph = graph_with([leaf("a")])

        apply_operation(
            graph, ReplaceStrategyOp(root=combine("c", leaf("x"), leaf("y")))
        )

        step = graph.steps["c"]
        assert (step.primary_input_id, step.secondary_input_id) == ("x", "y")
        assert sorted(graph.steps) == ["c", "x", "y"]

    def test_undo_round_trips_a_prior_shape(self) -> None:
        """What undo actually does: restore the tree captured before an edit."""
        graph = graph_with(
            [combine("c", leaf("a"), leaf("b"))], record_type="transcript"
        )
        before = graph.to_strategy_ast()
        assert before is not None

        apply_operation(graph, ReplaceStrategyOp(root=leaf("a")))
        assert sorted(graph.steps) == ["a"]

        apply_operation(graph, ReplaceStrategyOp(root=before.root))

        assert sorted(graph.steps) == ["a", "b", "c"]
        assert graph.roots == {"c"}

    def test_reports_the_steps_it_dropped(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        result = apply_operation(graph, ReplaceStrategyOp(root=leaf("a")))

        assert sorted(result.dropped_step_ids) == ["b", "c"]

    def test_name_and_description_are_applied_when_given(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(
            graph,
            ReplaceStrategyOp(root=leaf("a"), name="Renamed", description="why"),
        )

        assert (graph.name, graph.description) == ("Renamed", "why")

    def test_metadata_is_left_alone_when_omitted(self) -> None:
        graph = graph_with([leaf("a")])
        graph.name = "Original"
        graph.description = "keep me"

        apply_operation(graph, ReplaceStrategyOp(root=leaf("a")))

        assert (graph.name, graph.description) == ("Original", "keep me")

    def test_a_tree_with_a_duplicated_step_id_is_rejected(self) -> None:
        """WDK requires a step to belong to one position; a duplicate id would
        corrupt the graph's flat index rather than fail on push."""
        shared = leaf("dup")
        graph = graph_with([leaf("a")])
        bad = StrategyStepNode(
            id="root",
            search_name="__combine__",
            primary_input=shared,
            secondary_input=combine("mid", leaf("other"), shared.model_copy()),
            operator=CombineOp.INTERSECT,
        )

        with pytest.raises(ApplyError):
            apply_operation(graph, ReplaceStrategyOp(root=bad))
