"""The spec states every step the strategy holds before an edit is planned.

A live step no criterion names is one the next edit removes without being
asked to, and the strategy owns the shape of the part it holds.
"""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, StrategyAst

from pathfinder.domain.strategy.operational_spec import (
    SpecStructure,
    StructureNode,
    criteria_under,
    structure_criteria,
)
from pathfinder.domain.strategy.operations import DeleteResolution, DeleteStepOp
from pathfinder.domain.strategy.spec_hydration import spec_stating_the_live_tree

from ._builders import (
    applied,
    combine,
    expr_leaf,
    go_leaf,
    graph_of,
    plan,
    spec_of,
    text_leaf,
    tm_leaf,
)


def test_a_step_the_spec_leaves_out_is_stated_before_an_edit_plans_one() -> None:
    """An edit is planned against the structure, so every live step is in it."""
    root = combine("step_c2", combine("step_c1", text_leaf(), expr_leaf()), go_leaf())
    ast = StrategyAst(record_type="transcript", root=root)
    partial = spec_of(root)
    partial.criteria = [c for c in partial.criteria if c.id != "step_expr"]
    partial.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_text"),
                StructureNode(kind="leaf", criterion_id="step_go"),
            ],
        ),
    )

    stated = spec_stating_the_live_tree(partial, ast, sheet_params={})

    assert structure_criteria(stated.structure) == {
        "step_text",
        "step_expr",
        "step_go",
    }
    expr = next(c for c in stated.criteria if c.id == "step_expr")
    assert expr.search_name == "GenesByRNASeqEvidence"
    assert expr.resolved_params == dict(expr_leaf().parameters)


def test_the_strategy_owns_the_operator_of_the_part_it_holds() -> None:
    """The graph is what the strategy IS, so its operators are the stated ones."""
    root = combine("step_c2", combine("step_c1", text_leaf(), expr_leaf()), go_leaf())
    ast = StrategyAst(record_type="transcript", root=root)
    partial = spec_of(root)
    partial.criteria = [c for c in partial.criteria if c.id != "step_expr"]
    partial.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_text"),
                StructureNode(kind="leaf", criterion_id="step_go"),
            ],
        ),
    )

    stated = spec_stating_the_live_tree(partial, ast, sheet_params={})

    assert stated.structure is not None
    assert stated.structure.root.operator == CombineOp.INTERSECT
    assert structure_criteria(stated.structure) == {
        "step_text",
        "step_expr",
        "step_go",
    }
    joined = stated.structure.root.inputs[0]
    assert joined.operator == CombineOp.INTERSECT
    assert criteria_under(joined) == {"step_text", "step_expr"}


def test_every_join_of_the_built_part_is_the_one_the_graph_holds() -> None:
    """The plan's own joins are restated over the steps the strategy gained."""
    root = combine(
        "step_c3",
        combine("step_c2", combine("step_c1", text_leaf(), expr_leaf()), go_leaf()),
        tm_leaf(),
        operator=CombineOp.UNION,
    )
    ast = StrategyAst(record_type="transcript", root=root)
    partial = spec_of(root)
    partial.criteria = [
        c for c in partial.criteria if c.id not in {"step_go", "step_tm"}
    ]
    partial.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.MINUS,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_text"),
                StructureNode(kind="leaf", criterion_id="step_expr"),
            ],
        ),
    )

    stated = spec_stating_the_live_tree(partial, ast, sheet_params={})

    assert stated.structure is not None
    outer = stated.structure.root
    assert outer.operator == CombineOp.UNION
    assert outer.inputs[0].operator == CombineOp.INTERSECT
    assert outer.inputs[0].inputs[0].operator == CombineOp.INTERSECT
    assert structure_criteria(stated.structure) == {
        "step_text",
        "step_expr",
        "step_go",
        "step_tm",
    }


def test_an_edit_after_the_graft_writes_no_operator_the_plan_never_named() -> None:
    """Only the join the plan states reaches the strategy as an operator change."""
    root = combine(
        "step_c3",
        combine("step_c2", combine("step_c1", text_leaf(), expr_leaf()), go_leaf()),
        tm_leaf(),
        operator=CombineOp.UNION,
    )
    ast = StrategyAst(record_type="transcript", root=root)
    partial = spec_of(root)
    partial.criteria = [
        c for c in partial.criteria if c.id not in {"step_go", "step_tm"}
    ]
    partial.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.MINUS,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_text"),
                StructureNode(kind="leaf", criterion_id="step_expr"),
            ],
        ),
    )
    before = spec_stating_the_live_tree(partial, ast, sheet_params={})
    after = before.model_copy(deep=True)
    after.criteria = [c for c in after.criteria if c.id != "step_go"]
    after.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode(
                    kind="combine",
                    operator=CombineOp.MINUS,
                    inputs=[
                        StructureNode(kind="leaf", criterion_id="step_text"),
                        StructureNode(kind="leaf", criterion_id="step_expr"),
                    ],
                ),
                StructureNode(kind="leaf", criterion_id="step_tm"),
            ],
        ),
    )

    ops = plan(before, after, graph_of(root))

    assert [op.model_dump(include={"kind", "step_id"}) for op in ops] == [
        {"kind": "deleteStep", "step_id": "step_go"},
        {"kind": "updateCombineOperator", "step_id": "step_c1"},
    ]
    assert sorted(applied(root, ops).steps) == [
        "step_c1",
        "step_c3",
        "step_expr",
        "step_text",
        "step_tm",
    ]


def test_dropping_one_criterion_leaves_the_step_the_spec_had_left_out() -> None:
    """The reconciled spec names it, so the plan removes only what was dropped."""
    root = combine("step_c2", combine("step_c1", text_leaf(), expr_leaf()), go_leaf())
    ast = StrategyAst(record_type="transcript", root=root)
    partial = spec_of(root)
    partial.criteria = [c for c in partial.criteria if c.id != "step_expr"]
    partial.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_text"),
                StructureNode(kind="leaf", criterion_id="step_go"),
            ],
        ),
    )
    before = spec_stating_the_live_tree(partial, ast, sheet_params={})
    after = before.model_copy(deep=True)
    after.criteria = [c for c in after.criteria if c.id != "step_go"]
    after.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_text"),
                StructureNode(kind="leaf", criterion_id="step_expr"),
            ],
        ),
    )

    ops = plan(before, after, graph_of(root))

    assert ops == [
        DeleteStepOp(step_id="step_go", resolution=DeleteResolution.COLLAPSE_COMBINE)
    ]
    graph = applied(root, ops)
    assert sorted(graph.steps) == ["step_c1", "step_expr", "step_text"]
