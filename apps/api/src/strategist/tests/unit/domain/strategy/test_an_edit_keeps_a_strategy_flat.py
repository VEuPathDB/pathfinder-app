from __future__ import annotations

from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import CombineOp, StepFilter, StrategyStepNode

from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.operations import (
    AddCombineOp,
    GraphOperation,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
)
from strategist.tests._support.bound_values import bound
from strategist.tests.unit.domain.strategy._builders import (
    applied,
    combine,
    graph_of,
    leaf,
    plan,
    shape,
    spec_joined,
    spec_leaf,
    spec_of,
)


def _group_first() -> StrategyStepNode:
    return combine(
        "root",
        combine("group", leaf("pknoh"), leaf("pber"), CombineOp.UNION),
        leaf("ortho"),
    )


def _leaf_first() -> StrategyStepNode:
    return combine(
        "root",
        leaf("ortho"),
        combine("group", leaf("pknoh"), leaf("pber"), CombineOp.UNION),
    )


def _stated(root: StrategyStepNode, structure: StructureNode) -> OperationalSpec:
    spec = spec_of(root)
    return spec.model_copy(update={"structure": SpecStructure(root=structure)})


def _leaf_then_group(operator: CombineOp = CombineOp.INTERSECT) -> StructureNode:
    return spec_joined(
        operator,
        spec_leaf("ortho"),
        spec_joined(CombineOp.UNION, spec_leaf("pknoh"), spec_leaf("pber")),
    )


def _moved(spec: OperationalSpec, criterion_id: str) -> OperationalSpec:
    after = spec.model_copy(deep=True)
    for criterion in after.criteria:
        if criterion.id == criterion_id:
            criterion.resolved_params = {
                **criterion.resolved_params,
                **bound({"min_score": NumberValue(value=7)}),
            }
    return after


def test_a_value_edit_reads_a_group_first_strategy_as_its_stated_order() -> None:
    before = _stated(_group_first(), _leaf_then_group())

    ops = plan(before, _moved(before, "pknoh"), graph_of(_group_first()))

    assert [op.kind for op in ops] == ["updateStepParams"]


def test_a_value_edit_keeps_a_leaf_first_strategy_as_the_site_holds_it() -> None:
    before = _stated(_leaf_first(), _leaf_then_group())

    ops = plan(before, _moved(before, "pknoh"), graph_of(_leaf_first()))

    assert [op.kind for op in ops] == ["updateStepParams"]


def test_an_operator_edit_on_a_swapped_combine_mirrors_it() -> None:
    before = _stated(_group_first(), _leaf_then_group())
    after = before.model_copy(
        update={"structure": SpecStructure(root=_leaf_then_group(CombineOp.MINUS))}
    )

    ops = plan(before, after, graph_of(_group_first()))

    assert ops == [UpdateCombineOperatorOp(step_id="root", operator=CombineOp.RMINUS)]


def test_a_new_leaf_stated_first_joins_a_group_on_the_secondary_side() -> None:
    root = combine("group", leaf("pknoh"), leaf("pber"), CombineOp.UNION)
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.criteria.append(
        Criterion(id="ortho_new", text="an ortholog pattern", search_name="GenesByPfam")
    )
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.MINUS,
            spec_leaf("ortho_new"),
            spec_joined(CombineOp.UNION, spec_leaf("pknoh"), spec_leaf("pber")),
        )
    )

    ops = plan(before, after, graph_of(root))

    (added,) = [op for op in ops if isinstance(op, AddCombineOp)]
    assert (added.left_id, added.right_id) == ("group", "ortho_new")
    assert added.step.operator is CombineOp.RMINUS
    assert shape(applied(root, ops)) == "((pknoh UNION pber) RMINUS ortho_new)"


def test_a_restated_tree_puts_the_new_group_on_the_primary_side() -> None:
    root = combine(
        "root",
        combine("inner", leaf("ortho"), leaf("pknoh")),
        leaf("pber"),
    )
    before = spec_of(root)
    after = before.model_copy(
        update={
            "structure": SpecStructure(
                root=spec_joined(
                    CombineOp.INTERSECT,
                    spec_leaf("ortho"),
                    spec_joined(CombineOp.UNION, spec_leaf("pknoh"), spec_leaf("pber")),
                )
            )
        }
    )

    ops = plan(before, after, graph_of(root))

    (replaced,) = [op for op in ops if isinstance(op, ReplaceSubtreeOp)]
    restated = replaced.subtree
    assert restated.primary_input is not None
    assert restated.primary_input.operator is CombineOp.UNION
    assert restated.secondary_input is not None
    assert restated.secondary_input.id == "ortho"
    assert shape(applied(root, ops)) == "((pknoh UNION pber) INTERSECT ortho)"


def _grown(
    operator: CombineOp, filters: list[StepFilter] | None = None
) -> tuple[StrategyStepNode, list[GraphOperation]]:
    root = combine("root", leaf("ortho"), leaf("pknoh"), operator).model_copy(
        update={"filters": filters or []}
    )
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.criteria.append(
        Criterion(
            id="pber_new", text="essential in P. berghei", search_name="GenesByPfam"
        )
    )
    after.structure = SpecStructure(
        root=spec_joined(
            operator,
            spec_leaf("ortho"),
            spec_joined(CombineOp.UNION, spec_leaf("pknoh"), spec_leaf("pber_new")),
        )
    )
    return root, plan(before, after, graph_of(root))


def test_a_group_grown_on_the_secondary_side_moves_to_the_primary_side() -> None:
    root, ops = _grown(CombineOp.INTERSECT)

    assert shape(applied(root, ops)) == "((pknoh UNION pber_new) INTERSECT ortho)"
    assert "replaceSubtree" not in [op.kind for op in ops]


def test_a_minus_grown_on_the_secondary_side_mirrors() -> None:
    root, ops = _grown(CombineOp.MINUS)

    assert shape(applied(root, ops)) == "((pknoh UNION pber_new) RMINUS ortho)"
    assert "replaceSubtree" not in [op.kind for op in ops]


def test_a_combine_that_holds_a_filter_keeps_its_order() -> None:
    held = StepFilter(name="gene_boolean_filter_array", value={"values": ["YN"]})
    root, ops = _grown(CombineOp.INTERSECT, [held])

    assert shape(applied(root, ops)) == "(ortho INTERSECT (pknoh UNION pber_new))"
