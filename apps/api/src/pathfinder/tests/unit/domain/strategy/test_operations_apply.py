"""Applying one graph operation to the live graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import (
    CombineOp,
    StepKind,
    StrategyStep,
    StrategyStepNode,
)

from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
    AttachIntoSlot,
    AttachNewRoot,
    DeleteResolution,
    DeleteStepOp,
    DuplicateStepOp,
    GraphOperation,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
    UpdateStrategyMetaOp,
)
from pathfinder.domain.strategy.operations.apply import ApplyError, apply_operation
from pathfinder.domain.strategy.session import StrategyGraph

from ._builders import combine, graph_with, leaf, transform


class TestApplyAddLeaf:
    def test_new_root(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(graph, AddLeafOp(step=leaf("b"), attach=AttachNewRoot()))

        assert set(graph.steps) == {"a", "b"}
        assert graph.roots == {"a", "b"}

    def test_into_slot(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        apply_operation(
            graph,
            AddLeafOp(
                step=leaf("d"),
                attach=AttachIntoSlot(target_step_id="c", slot="primary"),
            ),
        )

        assert graph.steps["c"].primary_input_id == "d"

    def test_rejects_duplicate_id(self) -> None:
        graph = graph_with([leaf("a")])

        with pytest.raises(ApplyError):
            apply_operation(graph, AddLeafOp(step=leaf("a"), attach=AttachNewRoot()))


class TestApplyAddCombine:
    def test_creates_combine(self) -> None:
        graph = graph_with([leaf("a"), leaf("b")])

        apply_operation(
            graph,
            AddCombineOp(
                step=StrategyStepNode(
                    id="c", search_name="__combine__", operator=CombineOp.INTERSECT
                ),
                left_id="a",
                right_id="b",
            ),
        )

        step = graph.steps["c"]
        assert (step.primary_input_id, step.secondary_input_id) == ("a", "b")
        assert graph.roots == {"c"}

    def test_rejects_same_input(self) -> None:
        graph = graph_with([leaf("a")])

        with pytest.raises(ApplyError):
            apply_operation(
                graph,
                AddCombineOp(
                    step=StrategyStepNode(
                        id="c", search_name="__combine__", operator=CombineOp.INTERSECT
                    ),
                    left_id="a",
                    right_id="a",
                ),
            )


class TestApplyAddTransform:
    def test_before_consumer_inserts_between(self) -> None:
        graph = graph_with([transform("r", leaf("a"), search_name="x")])

        apply_operation(
            graph,
            AddTransformOp(
                step=StrategyStepNode(id="t", search_name="orthologs"),
                input_id="a",
                mode="before-consumer",
            ),
        )

        assert graph.steps["r"].primary_input_id == "t"
        assert graph.steps["t"].primary_input_id == "a"

    def test_new_root(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(
            graph,
            AddTransformOp(
                step=StrategyStepNode(id="t", search_name="orthologs"),
                input_id="a",
                mode="new-root",
            ),
        )

        assert graph.steps["t"].primary_input_id == "a"


class TestApplyDeleteStep:
    def test_collapse_combine_nested(self) -> None:
        inner = combine("C", leaf("A"), leaf("B"))
        graph = graph_with([combine("R", inner, leaf("D"))])

        result = apply_operation(
            graph,
            DeleteStepOp(step_id="A", resolution=DeleteResolution.COLLAPSE_COMBINE),
        )

        assert sorted(graph.steps) == ["B", "D", "R"]
        assert graph.steps["R"].primary_input_id == "B"
        assert sorted(result.dropped_step_ids) == ["A", "C"]

    def test_collapse_combine_root_secondary_leaf(self) -> None:
        inner = combine("text_or_go", leaf("text_kinases"), leaf("go_kinase_genes"))
        graph = graph_with([combine("narrowed", inner, leaf("pf_taxon"))])

        result = apply_operation(
            graph,
            DeleteStepOp(
                step_id="pf_taxon", resolution=DeleteResolution.COLLAPSE_COMBINE
            ),
        )

        assert sorted(graph.steps) == [
            "go_kinase_genes",
            "text_kinases",
            "text_or_go",
        ]
        assert sorted(result.dropped_step_ids) == ["narrowed", "pf_taxon"]

    def test_collapse_combine_root(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        apply_operation(
            graph,
            DeleteStepOp(step_id="a", resolution=DeleteResolution.COLLAPSE_COMBINE),
        )

        assert sorted(graph.steps) == ["b"]

    def test_promote_primary(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        apply_operation(
            graph,
            DeleteStepOp(step_id="c", resolution=DeleteResolution.PROMOTE_PRIMARY),
        )

        assert sorted(graph.steps) == ["a"]

    def test_promote_primary_on_a_transform_keeps_the_step_it_read(self) -> None:
        graph = graph_with([transform("t", combine("c", leaf("a"), leaf("b")))])

        result = apply_operation(
            graph,
            DeleteStepOp(step_id="t", resolution=DeleteResolution.PROMOTE_PRIMARY),
        )

        assert sorted(graph.steps) == ["a", "b", "c"]
        assert graph.primary_root_id() == "c"
        assert result.dropped_step_ids == ["t"]

    def test_a_delete_of_a_leaf_that_stands_alone_is_refused(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        with pytest.raises(ApplyError, match="reads no step"):
            apply_operation(
                graph,
                DeleteStepOp(step_id="a", resolution=DeleteResolution.PROMOTE_PRIMARY),
            )

    def test_delete_subtree_under_a_combine_takes_the_combine(self) -> None:
        """A combine with one branch gone combines nothing, so it leaves too."""
        inner = combine("c1", leaf("a"), leaf("b"))
        graph = graph_with([combine("c2", inner, leaf("d"))])

        result = apply_operation(
            graph,
            DeleteStepOp(step_id="a", resolution=DeleteResolution.DELETE_SUBTREE),
        )

        assert sorted(graph.steps) == ["b", "c2", "d"]
        assert graph.steps["c2"].primary_input_id == "b"
        assert sorted(result.dropped_step_ids) == ["a", "c1"]

    def test_delete_subtree_through_transform_cascades(self) -> None:
        chain = transform("r", transform("t", leaf("a")), search_name="x")
        graph = graph_with([chain])

        apply_operation(
            graph,
            DeleteStepOp(step_id="a", resolution=DeleteResolution.DELETE_SUBTREE),
        )

        assert sorted(graph.steps) == ["r"]
        assert graph.steps["r"].primary_input_id is None

    def test_delete_strategy_empties_graph(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(
            graph,
            DeleteStepOp(step_id="a", resolution=DeleteResolution.DELETE_STRATEGY),
        )

        assert graph.steps == {}
        assert graph.roots == set()

    def test_unknown_step_raises(self) -> None:
        graph = graph_with([leaf("a")])

        with pytest.raises(ApplyError):
            apply_operation(
                graph,
                DeleteStepOp(
                    step_id="missing", resolution=DeleteResolution.DELETE_STRATEGY
                ),
            )


class TestApplyReplaceSubtree:
    def test_swaps_subtree_under_parent(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        apply_operation(graph, ReplaceSubtreeOp(step_id="a", subtree=leaf("new_a")))

        assert "a" not in graph.steps
        assert graph.steps["c"].primary_input_id == "new_a"


class TestApplyUpdateOps:
    def test_update_step_params(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(
            graph,
            UpdateStepParamsOp(
                step_id="a", parameters={"foo": StringValue(value="bar")}
            ),
        )

        assert graph.steps["a"].parameters == {"foo": StringValue(value="bar")}

    def test_update_step_params_merges_into_existing(self) -> None:
        node = StrategyStepNode(
            id="a",
            search_name="geneById",
            parameters={
                "foo": StringValue(value="old"),
                "keep": StringValue(value="untouched"),
            },
        )
        graph = graph_with([node])

        apply_operation(
            graph,
            UpdateStepParamsOp(
                step_id="a", parameters={"foo": StringValue(value="new")}
            ),
        )

        assert graph.steps["a"].parameters == {
            "foo": StringValue(value="new"),
            "keep": StringValue(value="untouched"),
        }

    def test_update_combine_operator(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        apply_operation(
            graph,
            UpdateCombineOperatorOp(
                step_id="c", operator=CombineOp.UNION, colocation_params=None
            ),
        )

        assert graph.steps["c"].operator == CombineOp.UNION

    def test_update_step_meta(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(graph, UpdateStepMetaOp(step_id="a", display_name="renamed"))

        assert graph.steps["a"].display_name == "renamed"

    def test_update_strategy_meta(self) -> None:
        graph = graph_with([leaf("a")])

        apply_operation(
            graph,
            UpdateStrategyMetaOp(name="New name", description="New description"),
        )

        assert graph.name == "New name"
        assert graph.description == "New description"


class TestApplyDuplicateStep:
    def test_duplicates_under_parent(self) -> None:
        graph = graph_with([combine("c", leaf("a"), leaf("b"))])

        apply_operation(
            graph,
            DuplicateStepOp(
                source_step_id="a",
                duplicate_step_id="a_dup",
                combine_step_id="combine_dup",
            ),
        )

        duplicate = graph.steps["combine_dup"]
        assert "a_dup" in graph.steps
        assert (duplicate.primary_input_id, duplicate.secondary_input_id) == (
            "a",
            "a_dup",
        )
        # The original parent now points at the new combine in place of a.
        assert graph.steps["c"].primary_input_id == "combine_dup"

    def test_rejects_unknown_source(self) -> None:
        graph = graph_with([leaf("a")])

        with pytest.raises(ApplyError, match="missing"):
            apply_operation(
                graph,
                DuplicateStepOp(
                    source_step_id="missing",
                    duplicate_step_id="dup",
                    combine_step_id="cmb",
                ),
            )

    @pytest.mark.parametrize(
        ("source", "kind"),
        [("c", "combine"), ("t", "transform")],
    )
    def test_refuses_a_source_that_is_not_a_search(
        self, source: str, kind: str
    ) -> None:
        graph = graph_with([transform("t", combine("c", leaf("a"), leaf("b")))])

        with pytest.raises(ApplyError) as refused:
            apply_operation(
                graph,
                DuplicateStepOp(
                    source_step_id=source,
                    duplicate_step_id="dup",
                    combine_step_id="cmb",
                ),
            )

        assert str(refused.value) == (
            f"only a search step can be duplicated; step {source!r} is a {kind}"
        )
        assert set(graph.steps) == {"t", "c", "a", "b"}


PARITY_FIXTURE = (
    Path(__file__).resolve().parents[8] / "packages" / "spec" / "operations_parity.json"
)

_OP_ADAPTER: TypeAdapter[GraphOperation] = TypeAdapter(GraphOperation)


def _load_cases() -> list[dict[str, Any]]:
    return list(json.loads(PARITY_FIXTURE.read_text())["cases"])


def _build_graph(initial: dict[str, Any]) -> StrategyGraph:
    """The fixture describes steps by id, which is exactly what the graph holds."""
    graph = StrategyGraph(graph_id="g", name="g", site_id="plasmodb")
    for step in initial["steps"]:
        kind = StepKind(step.get("kind", "search"))
        graph.steps[step["id"]] = StrategyStep(
            id=step["id"],
            kind=kind,
            search_name=(
                None
                if kind is StepKind.COMBINE
                else "orthologs"
                if kind is StepKind.TRANSFORM
                else "geneById"
            ),
            primary_input_id=step.get("primaryInputStepId"),
            secondary_input_id=step.get("secondaryInputStepId"),
            operator=(CombineOp.INTERSECT if kind is StepKind.COMBINE else None),
        )
    graph.recompute_roots()
    return graph


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_parity_case(case: dict[str, Any]) -> None:
    graph = _build_graph(case["initial"])
    result = apply_operation(graph, _OP_ADAPTER.validate_python(case["op"]))
    expected = case["expected"]

    assert sorted(graph.steps) == sorted(expected["stepIds"])
    assert sorted(result.dropped_step_ids) == sorted(expected["droppedStepIds"])

    for parent_id, slots in expected["rootInputs"].items():
        node = graph.steps[parent_id]
        if "primary" in slots:
            assert node.primary_input_id == slots["primary"], parent_id
        if "secondary" in slots:
            assert node.secondary_input_id == slots["secondary"], parent_id
