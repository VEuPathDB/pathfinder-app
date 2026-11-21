from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, NumberValue
from veupathdb.domain.strategy import CombineOp

from strategist.domain.comparison_facts import ComparedVariant
from strategist.domain.strategy.edit_plan import node_for
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from strategist.domain.strategy.operations import ReplaceSubtreeOp
from strategist.domain.strategy.ranking import gene_scores, score_rows
from strategist.domain.strategy.reading_plan import plan_lines
from strategist.domain.strategy.spec_diff import diff_specs
from strategist.domain.strategy.spec_tree import build_step_tree
from strategist.tests._support.bound_values import bound
from strategist.tests.unit.domain.strategy._builders import sets_nothing

from ._builders import (
    applied,
    expr_leaf,
    graph_of,
    plan,
    spec_joined,
    spec_leaf,
    spec_of,
    three_step_root,
)


def _weighted(criterion_id: str, weight: int | None) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=criterion_id,
        search_name=f"GenesBy{criterion_id}",
        search_display_name=criterion_id,
        resolved_params=bound({"organism": MultiPickValue(values=["P. vivax"])}),
        weight=weight,
    )


def _ranking(*criteria: Criterion) -> OperationalSpec:
    root = spec_joined(CombineOp.UNION, *(spec_leaf(c.id) for c in criteria))
    return OperationalSpec(criteria=list(criteria), structure=SpecStructure(root=root))


def _reweighted(
    spec: OperationalSpec, criterion_id: str, weight: int
) -> OperationalSpec:
    after = spec.model_copy(deep=True)
    for criterion in after.criteria:
        if criterion.id == criterion_id:
            criterion.weight = weight
    return after


def test_a_criterion_weight_is_its_steps_weight() -> None:
    assert node_for(_weighted("peptide", 2)).wdk_weight == 2


def test_a_built_tree_weighs_each_leaf_as_its_criterion() -> None:
    tree = build_step_tree(_ranking(_weighted("a", 1), _weighted("b", 3)))

    leaves = [tree.root.primary_input, tree.root.secondary_input]
    assert [leaf.wdk_weight for leaf in leaves if leaf is not None] == [1, 3]


def test_a_spec_read_from_a_strategy_keeps_each_steps_weight() -> None:
    root = three_step_root()
    assert root.secondary_input is not None
    root.secondary_input.wdk_weight = 2

    spec = spec_of(root)

    assert {c.id: c.weight for c in spec.criteria} == {
        "step_text": None,
        "step_go": None,
        "step_expr": 2,
    }


def test_a_weight_change_changes_its_criterion() -> None:
    before = spec_of(three_step_root())

    diff = diff_specs(
        before, _reweighted(before, "step_expr", 2), sets_the_site=sets_nothing
    )

    assert [(c.criterion_id, c.disposition) for c in diff.changes] == [
        ("step_text", "kept"),
        ("step_go", "kept"),
        ("step_expr", "changed"),
    ]


def test_a_weight_change_restates_the_step_with_its_values() -> None:
    root = three_step_root()
    before = spec_of(root)

    ops = plan(before, _reweighted(before, "step_expr", 2), graph_of(root))

    [op] = ops
    assert isinstance(op, ReplaceSubtreeOp)
    assert op.step_id == "step_expr"
    step = applied(root, ops).steps["step_expr"]
    assert (step.wdk_weight, step.parameters) == (2, expr_leaf().parameters)


def test_a_plan_states_the_weight_of_each_weighted_search() -> None:
    lines = plan_lines(_ranking(_weighted("a", 1), _weighted("b", None)))

    assert lines == [
        '- a: GenesBya (a), organism=["P. vivax"], weight 1',
        '- b: GenesByb (b), organism=["P. vivax"]',
        "- structure: a UNION b",
    ]


def test_a_gene_scores_the_weights_of_the_searches_that_hold_it() -> None:
    held = {"a": {"g1", "g2", "g3"}, "b": {"g1", "g2"}, "c": {"g1", "g4"}}

    scores = gene_scores(held, {"a": 1, "b": 1, "c": 2}, {"g1", "g2", "g3", "g4"})

    assert list(scores.items()) == [(4, 1), (2, 2), (1, 1)]


def test_each_score_is_one_row_highest_first() -> None:
    rows = score_rows({3: 41, 1: 2_100}, top=3, title="Plan")

    assert rows == [
        ComparedVariant(label="Plan: score 3 of 3", gene_count=41),
        ComparedVariant(label="Plan: score 1 of 3", gene_count=2_100),
    ]


def test_an_edit_of_a_value_keeps_the_weight_the_step_holds() -> None:
    root = three_step_root()
    before = spec_of(root)
    assert root.secondary_input is not None
    root.secondary_input.wdk_weight = 5
    after = before.model_copy(deep=True)
    after.criteria[2].resolved_params = bound(
        {"min_expression_percentile": NumberValue(value=75)}
    )

    step = applied(root, plan(before, after, graph_of(root))).steps["step_expr"]

    assert (step.wdk_weight, step.parameters) == (
        5,
        {"min_expression_percentile": NumberValue(value=75)},
    )
