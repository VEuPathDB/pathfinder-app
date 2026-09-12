"""An edit becomes the smallest batch of operations over the live graph.

Every step the edit does not name keeps its id, so the WDK step behind it
survives the turn.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
    DeleteResolution,
    DeleteStepOp,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.spec_to_operations import UnsupportedEditError

from ._builders import (
    combine,
    expr_leaf,
    graph_of,
    plan,
    spec_leaf,
    spec_of,
    text_leaf,
    three_step_root,
)


def _edited(
    spec: OperationalSpec, criterion_id: str, **fields: object
) -> OperationalSpec:
    after = spec.model_copy(deep=True)
    for criterion in after.criteria:
        if criterion.id == criterion_id:
            for name, value in fields.items():
                setattr(criterion, name, value)
    return after


def test_operations_are_empty_when_the_diff_is_empty() -> None:
    root = three_step_root()
    before = spec_of(root)

    assert plan(before, before.model_copy(deep=True), graph_of(root)) == []


def test_kept_criterion_emits_no_operation() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = _edited(
        before,
        "step_expr",
        resolved_params={"min_expression_percentile": NumberValue(value=75)},
    )

    ops = plan(before, after, graph_of(root))

    assert [op.step_id for op in ops if isinstance(op, UpdateStepParamsOp)] == [
        "step_expr"
    ]
    assert len(ops) == 1


def test_changed_param_emits_update_step_params_on_the_same_step_id() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = _edited(
        before,
        "step_go",
        resolved_params={"organism": MultiPickValue(values=["P. vivax"])},
    )

    ops = plan(before, after, graph_of(root))

    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, UpdateStepParamsOp)
    assert op.step_id == "step_go"
    assert op.parameters["organism"] == MultiPickValue(values=["P. vivax"])


def test_a_changed_search_name_replaces_the_subtree_and_keeps_the_step_id() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = _edited(before, "step_expr", search_name="GenesByRNASeqSu")

    ops = plan(before, after, graph_of(root))

    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, ReplaceSubtreeOp)
    assert op.step_id == "step_expr"
    assert op.subtree.id == "step_expr"
    assert op.subtree.search_name == "GenesByRNASeqSu"


def test_a_dropped_param_replaces_the_subtree_rather_than_merging() -> None:
    """UpdateStepParamsOp merges, so a value the edit removes needs a replace."""
    root = three_step_root()
    before = spec_of(root)
    after = _edited(before, "step_expr", resolved_params={})

    ops = plan(before, after, graph_of(root))

    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, ReplaceSubtreeOp)
    assert op.subtree.parameters == {}


def test_dropped_criterion_emits_delete_step_with_collapse() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = spec_of(combine("step_c2", text_leaf(), expr_leaf()))
    # The reconstruction of the smaller tree renames nothing: the surviving
    # steps keep the ids the graph gave them.
    after.criteria = [c for c in before.criteria if c.id != "step_go"]
    after.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[spec_leaf("step_text"), spec_leaf("step_expr")],
        )
    )

    ops = plan(before, after, graph_of(root))

    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, DeleteStepOp)
    assert op.step_id == "step_go"
    assert op.resolution is DeleteResolution.COLLAPSE_COMBINE


def test_added_transform_emits_add_transform_with_the_current_root_as_input() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.criteria.append(
        Criterion(
            id="c_orthologs",
            text="map to P. vivax orthologs",
            search_name="GenesByOrthologs",
            role="transform",
            resolved_params={"organism": MultiPickValue(values=["P. vivax P01"])},
        )
    )
    assert before.structure is not None
    after.structure = SpecStructure(
        root=StructureNode(
            kind="transform",
            criterion_id="c_orthologs",
            inputs=[before.structure.root.model_copy(deep=True)],
        )
    )

    ops = plan(before, after, graph_of(root))

    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, AddTransformOp)
    assert op.input_id == "step_c2"
    assert op.mode == "new-root"
    assert op.step.id == "c_orthologs"
    assert op.step.search_name == "GenesByOrthologs"


def test_added_leaf_joins_the_current_root_with_the_declared_operator() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.criteria.append(
        Criterion(
            id="c_secreted",
            text="predicted secreted",
            search_name="GenesBySignalPeptide",
        )
    )
    assert before.structure is not None
    after.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                before.structure.root.model_copy(deep=True),
                spec_leaf("c_secreted"),
            ],
        )
    )

    ops = plan(before, after, graph_of(root))

    assert len(ops) == 2
    add_leaf, add_combine = ops
    assert isinstance(add_leaf, AddLeafOp)
    assert add_leaf.step.id == "c_secreted"
    assert isinstance(add_combine, AddCombineOp)
    assert add_combine.left_id == "step_c2"
    assert add_combine.right_id == "c_secreted"
    assert add_combine.step.operator is CombineOp.INTERSECT


def test_a_changed_combine_operator_updates_the_combine_in_place() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = before.model_copy(deep=True)
    assert after.structure is not None
    after.structure.root.inputs[0].operator = CombineOp.UNION

    ops = plan(before, after, graph_of(root))

    assert len(ops) == 1
    op = ops[0]
    assert isinstance(op, UpdateCombineOperatorOp)
    assert op.step_id == "step_c1"
    assert op.operator is CombineOp.UNION


def test_a_changed_criterion_that_names_no_step_is_refused() -> None:
    """A FRAME-authored label addresses nothing in the live graph."""
    labelled = OperationalSpec(
        goal="find proteases",
        record_type="transcript",
        criteria=[
            Criterion(
                id="c1_protease_text",
                text="protease text",
                search_name="GenesByText",
                resolved_params={"organism": MultiPickValue(values=["Plasmodium"])},
            )
        ],
        structure=SpecStructure(root=spec_leaf("c1_protease_text")),
    )
    after = labelled.model_copy(deep=True)
    after.criteria[0].resolved_params["organism"] = MultiPickValue(values=["P. vivax"])

    with pytest.raises(UnsupportedEditError):
        plan(labelled, after, graph_of(three_step_root()))
