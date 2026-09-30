"""A UNION that joins a criterion the strategy held to an arm added this turn
needs a stated OR over those arms."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.combination_check import (
    UnstatedUnion,
    unstated_union,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)

# The tritrypdb conversation: the DAL972 step the strategy held, and the
# TREU927 arm the comparison question added.
_DAL972 = Criterion(
    id="step_dd5b456c",
    text="DAL972 genes with an RNA-binding domain",
    search_name="GenesByInterproDomain",
)
_TREU927 = Criterion(
    id="c_treu927_rna_binding_domains",
    text="TREU927 genes with the same RNA-binding domains",
    search_name="GenesByInterproDomain",
)
_SIGNAL = Criterion(
    id="step_signal", text="signal peptide", search_name="GenesWithSignalPeptide"
)
_GPI = Criterion(id="c_gpi", text="GPI anchor", search_name="GenesByText")
_CRITERIA = [_DAL972, _TREU927, _SIGNAL, _GPI]


def _leaf(criterion: Criterion) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion.id)


def _join(operator: CombineOp, *inputs: StructureNode) -> SpecStructure:
    return SpecStructure(
        root=StructureNode(kind="combine", operator=operator, inputs=list(inputs))
    )


def _or(expression: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value=expression,
        label="how the requirements combine",
        source=ConstraintSource.USER_EXPLICIT,
    )


def test_a_union_of_the_held_root_and_a_new_arm_is_unstated() -> None:
    tree = _join(CombineOp.UNION, _leaf(_DAL972), _leaf(_TREU927))

    found = unstated_union(tree, {_DAL972.id}, [], _CRITERIA)

    assert found == UnstatedUnion(
        held=("step_dd5b456c",), added=("c_treu927_rna_binding_domains",)
    )


def test_an_intersect_of_the_held_root_and_a_new_arm_is_no_union() -> None:
    joined = [
        unstated_union(
            _join(op, _leaf(_DAL972), _leaf(_TREU927)), {_DAL972.id}, [], _CRITERIA
        )
        for op in (CombineOp.INTERSECT, CombineOp.UNION)
    ]

    assert joined == [
        None,
        UnstatedUnion(
            held=("step_dd5b456c",), added=("c_treu927_rna_binding_domains",)
        ),
    ]


def test_a_union_of_two_held_criteria_is_the_researchers_edit() -> None:
    """Flipping a held combine to UNION adds no arm the strategy did not hold."""
    tree = _join(CombineOp.UNION, _leaf(_DAL972), _leaf(_SIGNAL))

    found = [
        unstated_union(tree, held, [], _CRITERIA)
        for held in ({_DAL972.id, _SIGNAL.id}, {_DAL972.id})
    ]

    assert found == [
        None,
        UnstatedUnion(held=("step_dd5b456c",), added=("step_signal",)),
    ]


def test_a_first_build_holds_nothing_to_join() -> None:
    tree = _join(CombineOp.UNION, _leaf(_GPI), _leaf(_SIGNAL))

    found = [
        unstated_union(tree, held, [], _CRITERIA) for held in (set(), {_SIGNAL.id})
    ]

    assert found == [None, UnstatedUnion(held=("step_signal",), added=("c_gpi",))]


def test_a_stated_or_over_both_arms_allows_the_union() -> None:
    tree = _join(CombineOp.UNION, _leaf(_SIGNAL), _leaf(_GPI))

    found = [
        unstated_union(tree, {_SIGNAL.id}, stated, _CRITERIA)
        for stated in ([_or("signal peptide OR GPI anchor")], [])
    ]

    assert found == [None, UnstatedUnion(held=("step_signal",), added=("c_gpi",))]


def test_a_stated_or_over_other_criteria_does_not_cover_the_arms() -> None:
    tree = _join(CombineOp.UNION, _leaf(_DAL972), _leaf(_TREU927))

    found = unstated_union(
        tree, {_DAL972.id}, [_or("signal peptide OR GPI anchor")], _CRITERIA
    )

    assert found == UnstatedUnion(
        held=("step_dd5b456c",), added=("c_treu927_rna_binding_domains",)
    )


def test_a_new_filter_inside_a_held_union_is_no_new_arm() -> None:
    held_union = StructureNode(
        kind="combine",
        operator=CombineOp.UNION,
        inputs=[
            _leaf(_DAL972),
            StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[_leaf(_SIGNAL), _leaf(_GPI)],
            ),
        ],
    )

    found = [
        unstated_union(SpecStructure(root=held_union), held, [], _CRITERIA)
        for held in ({_DAL972.id, _SIGNAL.id}, {_DAL972.id})
    ]

    assert found == [
        None,
        UnstatedUnion(held=("step_dd5b456c",), added=("c_gpi", "step_signal")),
    ]


def test_an_assumed_or_is_no_statement() -> None:
    tree = _join(CombineOp.UNION, _leaf(_SIGNAL), _leaf(_GPI))
    assumed = _or("signal peptide OR GPI anchor").model_copy(
        update={"source": ConstraintSource.ASSUMED}
    )

    assert unstated_union(tree, {_SIGNAL.id}, [assumed], _CRITERIA) == UnstatedUnion(
        held=("step_signal",), added=("c_gpi",)
    )
