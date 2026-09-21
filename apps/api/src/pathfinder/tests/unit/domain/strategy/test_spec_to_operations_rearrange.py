"""Re-nesting the steps that stay, and the rewires the planner refuses.

A leaf keeps its id through a rearrangement, so the WDK step and the revision
behind it survive.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import (
    CombineOp,
    StepKind,
    StrategyStep,
    StrategyStepNode,
)

from pathfinder.domain.strategy.edit_plan import UnsupportedEditError
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import (
    AddLeafOp,
    DeleteStepOp,
    ReplaceSubtreeOp,
    WireInputOp,
)

from ._builders import (
    applied,
    combine,
    expr_leaf,
    go_leaf,
    graph_of,
    plan,
    shape,
    spec_joined,
    spec_leaf,
    spec_of,
    text_leaf,
    three_step_root,
    tm_leaf,
    transform_over,
)


def _rearranged(root: StrategyStepNode) -> OperationalSpec:
    """The same three criteria, nested as ``text AND (go AND expr)``."""
    after = spec_of(root).model_copy(deep=True)
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT,
            spec_leaf("step_text"),
            spec_joined(
                CombineOp.INTERSECT, spec_leaf("step_go"), spec_leaf("step_expr")
            ),
        )
    )
    return after


def test_a_rearrangement_of_the_steps_that_stay_replaces_the_combines() -> None:
    """Re-nesting the surviving steps is one replacement above the leaves."""
    root = three_step_root()

    ops = plan(spec_of(root), _rearranged(root), graph_of(root))

    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, ReplaceSubtreeOp)
    assert op.step_id == "step_c2"
    assert shape(applied(root, ops)) == (
        "(step_text INTERSECT (step_go INTERSECT step_expr))"
    )


def test_a_rearrangement_keeps_every_leaf_step_id() -> None:
    root = three_step_root()

    ops = plan(spec_of(root), _rearranged(root), graph_of(root))
    graph = applied(root, ops)

    assert {"step_text", "step_go", "step_expr"} <= set(graph.steps)
    assert not [op for op in ops if isinstance(op, (AddLeafOp, DeleteStepOp))]


def test_a_rearrangement_reuses_the_combine_whose_inputs_do_not_move() -> None:
    """A combine over an unchanged ordered pair keeps its id and its WDK step."""
    root = combine(
        "step_c3",
        combine("step_c1", text_leaf(), go_leaf()),
        combine("step_c2", expr_leaf(), tm_leaf()),
    )
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.UNION,
            spec_joined(
                CombineOp.INTERSECT, spec_leaf("step_text"), spec_leaf("step_go")
            ),
            spec_joined(
                CombineOp.INTERSECT, spec_leaf("step_tm"), spec_leaf("step_expr")
            ),
        )
    )

    graph = applied(root, plan(before, after, graph_of(root)))

    assert graph.steps["step_c1"].primary_input_id == "step_text"
    assert graph.steps["step_c1"].secondary_input_id == "step_go"
    assert "step_c2" not in graph.steps
    assert shape(graph) == (
        "((step_text INTERSECT step_go) UNION (step_tm INTERSECT step_expr))"
    )


def test_a_moved_transform_is_rewired_and_keeps_its_step_id() -> None:
    """The structure states the transform's input, so the edit may move it."""
    root = transform_over(combine("step_c1", text_leaf(), go_leaf()))
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT,
            StructureNode(
                kind="transform",
                criterion_id="step_orth",
                inputs=[spec_leaf("step_text")],
            ),
            spec_leaf("step_go"),
        )
    )

    graph = applied(root, plan(before, after, graph_of(root)))

    assert graph.steps["step_orth"].search_name == "GenesByOrthologs"
    assert shape(graph) == "(step_orth[step_text] INTERSECT step_go)"


def test_a_rearrangement_that_drops_a_surviving_leaf_is_refused() -> None:
    """A criterion the edit keeps must hold a position in the new shape."""
    root = three_step_root()
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT, spec_leaf("step_text"), spec_leaf("step_go")
        )
    )

    with pytest.raises(UnsupportedEditError) as excinfo:
        plan(before, after, graph_of(root))

    assert "step_expr" in str(excinfo.value)


def _nested_over(first_criterion: str) -> SpecStructure:
    return SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT,
            spec_leaf(first_criterion),
            spec_joined(
                CombineOp.INTERSECT,
                spec_leaf("step_text"),
                spec_joined(
                    CombineOp.INTERSECT, spec_leaf("step_go"), spec_leaf("step_expr")
                ),
            ),
        )
    )


def test_a_rearrangement_builds_the_criterion_the_strategy_never_held() -> None:
    """A criterion the baseline states with no step is one the rewire adds."""
    root = three_step_root()
    before = spec_of(root)
    before.criteria.append(
        Criterion(id="c_unbuilt", text="never built", search_name="GenesByTaxon")
    )
    after = before.model_copy(deep=True)
    after.structure = _nested_over("c_unbuilt")

    graph = applied(root, plan(before, after, graph_of(root)))

    assert graph.steps["c_unbuilt"].search_name == "GenesByTaxon"
    assert shape(graph) == (
        "(c_unbuilt INTERSECT (step_text INTERSECT (step_go INTERSECT step_expr)))"
    )


def test_a_rearrangement_that_adopts_a_step_from_outside_is_refused() -> None:
    """An edit rewires the strategy's own steps and adopts no stray."""
    root = three_step_root()
    graph = graph_of(root)
    graph.steps["step_stray"] = StrategyStep(
        id="step_stray", kind=StepKind.SEARCH, search_name="GenesByTaxon"
    )
    graph.recompute_roots()
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.criteria.append(
        Criterion(id="step_stray", text="a detached step", search_name="GenesByTaxon")
    )
    after.structure = _nested_over("step_stray")

    with pytest.raises(UnsupportedEditError) as excinfo:
        plan(before, after, graph)

    assert "step_stray" in str(excinfo.value)


def test_a_new_criterion_rewires_an_occupied_slot_without_evicting_its_step() -> None:
    """The wire the planner emits puts the slot's own step under the new combine."""
    root = combine("step_c1", text_leaf(), go_leaf())
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.criteria.append(
        Criterion(id="step_tm", text="two or more TM domains", search_name="tm")
    )
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT,
            spec_joined(
                CombineOp.INTERSECT, spec_leaf("step_text"), spec_leaf("step_tm")
            ),
            spec_leaf("step_go"),
        )
    )
    graph = graph_of(root)
    assert graph.steps["step_c1"].primary_input_id == "step_text"

    ops = plan(before, after, graph)

    wires = [op for op in ops if isinstance(op, WireInputOp)]
    assert len(wires) == 1
    assert wires[0].target_step_id == "step_c1"
    assert wires[0].slot == "primary"
    assert shape(applied(root, ops)) == (
        "((step_text INTERSECT step_tm) INTERSECT step_go)"
    )
