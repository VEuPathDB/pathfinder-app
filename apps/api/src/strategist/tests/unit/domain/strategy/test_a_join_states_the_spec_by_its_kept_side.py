from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from strategist.domain.strategy.operational_spec import SpecStructure
from strategist.domain.strategy.spec_edit_guard import (
    JoinContradiction,
    contradicted_joins,
)

from ._builders import combine, graph_of, leaf, spec_joined, spec_leaf


def test_a_mirrored_join_with_its_sides_swapped_states_the_spec() -> None:
    graph = graph_of(combine("step_root", leaf("c_k"), leaf("c_e"), CombineOp.RMINUS))
    structure = SpecStructure(
        root=spec_joined(CombineOp.MINUS, spec_leaf("c_e"), spec_leaf("c_k"))
    )

    assert contradicted_joins(structure, graph, ["c_e", "c_k"]) == {}


def test_a_mirrored_join_on_the_same_sides_departs_from_the_spec() -> None:
    graph = graph_of(combine("step_root", leaf("c_e"), leaf("c_k"), CombineOp.RMINUS))
    structure = SpecStructure(
        root=spec_joined(CombineOp.MINUS, spec_leaf("c_e"), spec_leaf("c_k"))
    )

    assert contradicted_joins(structure, graph, ["c_e", "c_k"]) == {
        frozenset({"c_e", "c_k"}): JoinContradiction(
            declared=CombineOp.MINUS, written=CombineOp.RMINUS
        )
    }


@pytest.mark.parametrize("operator", [CombineOp.MINUS, CombineOp.LONLY])
def test_a_one_sided_join_over_swapped_sides_departs_from_the_spec(
    operator: CombineOp,
) -> None:
    graph = graph_of(combine("step_root", leaf("c_k"), leaf("c_e"), operator))
    structure = SpecStructure(
        root=spec_joined(operator, spec_leaf("c_e"), spec_leaf("c_k"))
    )

    assert contradicted_joins(structure, graph, ["c_e", "c_k"]) == {
        frozenset({"c_e", "c_k"}): JoinContradiction(
            declared=operator, written=operator
        )
    }


def test_a_symmetric_join_over_swapped_sides_states_the_spec() -> None:
    graph = graph_of(
        combine("step_root", leaf("c_k"), leaf("c_e"), CombineOp.INTERSECT)
    )
    structure = SpecStructure(
        root=spec_joined(CombineOp.INTERSECT, spec_leaf("c_e"), spec_leaf("c_k"))
    )

    assert contradicted_joins(structure, graph, ["c_e", "c_k"]) == {}


def _folded(operator: CombineOp, ids: list[str]) -> StrategyStepNode:
    tree = leaf(ids[0])
    for index, criterion_id in enumerate(ids[1:]):
        tree = combine(f"step_join_{index}", tree, leaf(criterion_id), operator)
    return tree


@pytest.mark.parametrize("operator", [CombineOp.MINUS, CombineOp.LONLY])
@pytest.mark.parametrize("count", [2, 3, 4])
def test_a_one_sided_join_over_many_inputs_folded_left_states_the_spec(
    operator: CombineOp, count: int
) -> None:
    ids = [f"c_{index}" for index in range(count)]
    structure = SpecStructure(root=spec_joined(operator, *(spec_leaf(i) for i in ids)))

    assert contradicted_joins(structure, graph_of(_folded(operator, ids)), ids) == {}


@pytest.mark.parametrize("operator", [CombineOp.MINUS, CombineOp.LONLY])
def test_a_one_sided_join_over_many_inputs_reversed_departs_from_the_spec(
    operator: CombineOp,
) -> None:
    ids = ["c_0", "c_1", "c_2"]
    reversed_tree = combine(
        "step_root",
        leaf("c_2"),
        combine("step_inner", leaf("c_0"), leaf("c_1"), operator),
        operator,
    )
    structure = SpecStructure(root=spec_joined(operator, *(spec_leaf(i) for i in ids)))

    assert contradicted_joins(structure, graph_of(reversed_tree), ids) == {
        frozenset(ids): JoinContradiction(declared=operator, written=operator)
    }


@pytest.mark.parametrize("operator", [CombineOp.MINUS, CombineOp.LONLY])
def test_a_one_sided_join_nested_on_the_right_departs_from_the_spec(
    operator: CombineOp,
) -> None:
    ids = ["c_0", "c_1", "c_2"]
    nested = combine(
        "step_root",
        leaf("c_0"),
        combine("step_inner", leaf("c_1"), leaf("c_2"), operator),
        operator,
    )
    structure = SpecStructure(root=spec_joined(operator, *(spec_leaf(i) for i in ids)))

    assert contradicted_joins(structure, graph_of(nested), ids) == {
        frozenset({"c_1", "c_2"}): JoinContradiction(
            declared=operator, written=operator
        )
    }


@pytest.mark.parametrize(
    ("operator", "mirrored"),
    [(CombineOp.MINUS, CombineOp.RMINUS), (CombineOp.LONLY, CombineOp.RONLY)],
)
def test_a_mirrored_join_nested_on_its_kept_side_departs_from_the_spec(
    operator: CombineOp, mirrored: CombineOp
) -> None:
    ids = ["c_0", "c_1", "c_2"]
    nested = combine(
        "step_root",
        combine("step_inner", leaf("c_2"), leaf("c_1"), mirrored),
        leaf("c_0"),
        mirrored,
    )
    structure = SpecStructure(root=spec_joined(operator, *(spec_leaf(i) for i in ids)))

    assert contradicted_joins(structure, graph_of(nested), ids) == {
        frozenset({"c_1", "c_2"}): JoinContradiction(
            declared=operator, written=mirrored
        )
    }
