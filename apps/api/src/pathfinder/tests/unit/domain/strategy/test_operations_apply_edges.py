"""Cutting an edge: detach, collapse, and orphan-sibling.

Detach is not delete, so the freed subtree stays in the graph as its own root;
``StrategyAst.detached_roots`` is that component's home. WDK never sees it,
which is precisely what the delete dialog promises.
"""

from __future__ import annotations

import pytest
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import TypeAdapter, ValidationError

from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.domain.strategy.graph_model import rebuild_tree
from pathfinder.domain.strategy.operations import (
    DeleteEdgeOp,
    DeleteEdgeResolution,
    DeleteResolution,
    DeleteStepOp,
    GraphOperation,
)
from pathfinder.domain.strategy.operations.apply import ApplyError, apply_operation
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.tree import walk

from ._builders import combine, graph_with, leaf


class _Request(CamelModel):
    """Mirrors the apply-operation request, so the wire shape is exercised."""

    op: GraphOperation


def _pair_graph() -> StrategyGraph:
    return graph_with([combine("c", leaf("a"), leaf("b"))], record_type="transcript")


def _cut(source_id: str, slot: str, resolution: DeleteEdgeResolution) -> DeleteEdgeOp:
    return DeleteEdgeOp(
        source_id=source_id, target_id="c", slot=slot, resolution=resolution
    )


def _detach(source_id: str, slot: str) -> DeleteEdgeOp:
    return _cut(source_id, slot, DeleteEdgeResolution.DETACH)


def _orphan(step_id: str) -> DeleteStepOp:
    return DeleteStepOp(step_id=step_id, resolution=DeleteResolution.ORPHAN_SIBLING)


class TestWireContract:
    """The operation union must carry the tags the canvas sends."""

    def test_delete_edge_parses_from_the_wire(self) -> None:
        request = _Request.model_validate(
            {
                "op": {
                    "kind": "deleteEdge",
                    "sourceId": "b",
                    "targetId": "c",
                    "slot": "secondary",
                    "resolution": "detach",
                }
            }
        )

        assert request.op == DeleteEdgeOp(
            source_id="b",
            target_id="c",
            slot="secondary",
            resolution=DeleteEdgeResolution.DETACH,
        )

    def test_slot_is_constrained_to_the_two_wdk_inputs(self) -> None:
        with pytest.raises(ValidationError):
            _Request.model_validate(
                {
                    "op": {
                        "kind": "deleteEdge",
                        "sourceId": "b",
                        "targetId": "c",
                        "slot": "tertiary",
                        "resolution": "detach",
                    }
                }
            )

    def test_round_trips_through_camel_case(self) -> None:
        op = _cut("b", "primary", DeleteEdgeResolution.COLLAPSE)
        adapter = TypeAdapter(GraphOperation)

        restored = adapter.validate_python(op.model_dump(by_alias=True, mode="json"))

        assert restored == op

    def test_the_orphan_sibling_resolution_exists(self) -> None:
        assert DeleteResolution("orphan-sibling") is DeleteResolution.ORPHAN_SIBLING

    def test_orphan_sibling_parses_from_the_wire(self) -> None:
        op = DeleteStepOp.model_validate(
            {"kind": "deleteStep", "stepId": "b", "resolution": "orphan-sibling"}
        )

        assert op.resolution == DeleteResolution.ORPHAN_SIBLING


class TestDetach:
    def test_clears_the_named_slot(self) -> None:
        graph = _pair_graph()

        apply_operation(graph, _detach("b", "secondary"))

        step = graph.steps["c"]
        assert (step.primary_input_id, step.secondary_input_id) == ("a", None)

    def test_clears_combine_fields_that_need_the_slot(self) -> None:
        """An operator without a second input is not a combine any more."""
        graph = _pair_graph()

        apply_operation(graph, _detach("b", "secondary"))

        step = graph.steps["c"]
        assert (step.operator, step.colocation_params) == (None, None)

    def test_detached_source_survives_as_its_own_root(self) -> None:
        graph = _pair_graph()

        apply_operation(graph, _detach("b", "secondary"))

        assert "b" in graph.steps
        assert graph.roots == {"b", "c"}

    def test_reports_no_dropped_steps(self) -> None:
        graph = _pair_graph()

        result = apply_operation(graph, _detach("b", "secondary"))

        assert result.dropped_step_ids == []

    def test_detaching_primary_promotes_the_surviving_secondary(self) -> None:
        """A node cannot hold a secondary input alone, so the survivor moves up."""
        graph = _pair_graph()

        apply_operation(graph, _detach("a", "primary"))

        step = graph.steps["c"]
        assert (step.primary_input_id, step.secondary_input_id) == ("b", None)
        assert graph.roots == {"a", "c"}

    def test_the_detached_node_still_projects_to_wdk(self) -> None:
        """A detached graph must still project to the nested shape WDK accepts."""
        graph = _pair_graph()

        apply_operation(graph, _detach("a", "primary"))

        dumped = rebuild_tree("c", graph.steps).model_dump(by_alias=True, mode="json")
        restored = StrategyStepNode.model_validate(dumped)
        assert restored.primary_input is not None
        assert restored.primary_input.id == "b"

    def test_unknown_target_is_rejected(self) -> None:
        graph = graph_with([leaf("a")])

        with pytest.raises(ApplyError):
            apply_operation(
                graph,
                DeleteEdgeOp(
                    source_id="a",
                    target_id="missing",
                    slot="primary",
                    resolution=DeleteEdgeResolution.DETACH,
                ),
            )

    def test_slot_that_is_not_wired_to_the_source_is_rejected(self) -> None:
        graph = _pair_graph()

        with pytest.raises(ApplyError):
            apply_operation(graph, _detach("b", "primary"))


class TestCollapse:
    def test_removes_the_combine_and_its_secondary_subtree(self) -> None:
        graph = _pair_graph()

        result = apply_operation(
            graph, _cut("c", "secondary", DeleteEdgeResolution.COLLAPSE)
        )

        assert "c" not in graph.steps
        assert "b" not in graph.steps
        assert graph.roots == {"a"}
        assert set(result.dropped_step_ids) == {"b", "c"}


def _nested_graph() -> StrategyGraph:
    """``((a INTERSECT b) INTERSECT e)``."""
    inner = combine("c", leaf("a"), leaf("b"))
    return graph_with([combine("d", inner, leaf("e"))], record_type="transcript")


class TestOrphanSibling:
    def test_deletes_only_the_targets_subtree(self) -> None:
        graph = _pair_graph()

        result = apply_operation(graph, _orphan("b"))

        assert "b" not in graph.steps
        assert result.dropped_step_ids == ["b"]

    def test_keeps_the_combine_and_the_surviving_branch(self) -> None:
        graph = _pair_graph()

        apply_operation(graph, _orphan("b"))

        assert sorted(graph.steps) == ["a", "c"]

    def test_clears_the_slot_that_pointed_at_the_target(self) -> None:
        graph = _pair_graph()

        apply_operation(graph, _orphan("b"))

        step = graph.steps["c"]
        assert (step.secondary_input_id, step.operator) == (None, None)

    def test_detaches_the_parent_from_its_own_parent(self) -> None:
        graph = _nested_graph()

        apply_operation(graph, _orphan("b"))

        outer = graph.steps["d"]
        assert (outer.primary_input_id, outer.secondary_input_id) == ("e", None)
        assert "c" in graph.roots

    def test_the_orphaned_component_survives_serialization(self) -> None:
        """The survivors have somewhere to live, so the delete is written down."""
        graph = _nested_graph()

        apply_operation(graph, _orphan("b"))
        ast = graph.to_strategy_ast()

        assert ast is not None
        assert {node.id for node in ast.detached_roots} == {"c"}

    def test_every_surviving_step_is_still_represented(self) -> None:
        graph = _nested_graph()

        apply_operation(graph, _orphan("b"))
        ast = graph.to_strategy_ast()

        assert ast is not None
        seen = {node.id for node in walk(ast.root)}
        for detached in ast.detached_roots:
            seen |= {node.id for node in walk(detached)}
        assert seen == {"a", "c", "d", "e"}

    def test_promotes_the_survivor_when_the_primary_slot_is_cleared(self) -> None:
        graph = _pair_graph()

        apply_operation(graph, _orphan("a"))

        step = graph.steps["c"]
        assert (step.primary_input_id, step.secondary_input_id) == ("b", None)

    def test_deletes_the_whole_subtree_under_the_target(self) -> None:
        deep = combine("t", leaf("t1"), leaf("t2"))
        graph = graph_with([combine("c", leaf("a"), deep)], record_type="transcript")

        result = apply_operation(graph, _orphan("t"))

        assert {"t", "t1", "t2"}.isdisjoint(graph.steps)
        assert set(result.dropped_step_ids) == {"t", "t1", "t2"}

    def test_a_root_level_step_has_no_combine_parent(self) -> None:
        graph = graph_with([leaf("a")], record_type="transcript")

        with pytest.raises(ApplyError):
            apply_operation(graph, _orphan("a"))

    def test_unknown_step_is_rejected(self) -> None:
        graph = _pair_graph()

        with pytest.raises(ApplyError):
            apply_operation(graph, _orphan("missing"))
