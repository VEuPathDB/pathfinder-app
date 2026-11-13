"""The combine a set of criteria meets at in the tree."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from strategist.domain.strategy.combination_check import meeting_operator
from strategist.domain.strategy.operational_spec import (
    SpecStructure,
    StructureNode,
)


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _combine(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _meeting(structure: SpecStructure, criterion_ids: list[str]) -> str:
    """The operator the criteria meet at, empty when they never meet."""
    operator = meeting_operator(structure, criterion_ids)
    return "" if operator is None else operator.value


class TestMeetingOperator:
    def test_two_leaves_under_one_combine_meet_at_its_operator(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi"))
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION

    def test_a_nested_branch_is_the_meeting_node_not_the_root(self) -> None:
        structure = SpecStructure(
            root=_combine(
                CombineOp.INTERSECT,
                _leaf("c_kinase"),
                _combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi")),
            )
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION
        assert meeting_operator(structure, ["c_kinase", "c_ms"]) is CombineOp.INTERSECT

    def test_a_transform_between_the_leaves_and_the_combine_is_transparent(
        self,
    ) -> None:
        structure = SpecStructure(
            root=_combine(
                CombineOp.UNION,
                StructureNode(
                    kind="transform", criterion_id="c_ortho", inputs=[_leaf("c_ms")]
                ),
                _leaf("c_derisi"),
            )
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION

    def test_a_transform_above_the_meeting_combine_is_transparent(self) -> None:
        structure = SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="c_ortho",
                inputs=[_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi"))],
            )
        )

        assert meeting_operator(structure, ["c_ms", "c_derisi"]) is CombineOp.UNION

    def test_three_criteria_meet_at_the_combine_that_holds_them_all(self) -> None:
        structure = SpecStructure(
            root=_combine(
                CombineOp.INTERSECT,
                _combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi")),
                _leaf("c_kinase"),
            )
        )

        assert (
            meeting_operator(structure, ["c_ms", "c_derisi", "c_kinase"])
            is CombineOp.INTERSECT
        )

    def test_an_absent_criterion_has_no_meeting_node(self) -> None:
        structure = SpecStructure(
            root=_combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_kinase"))
        )

        assert _meeting(structure, ["c_ms", "c_derisi"]) == ""


class TestDuplicateLeaves:
    """A duplicated leaf cannot stand in for a criterion that meets elsewhere."""

    def test_a_union_of_one_criterion_with_itself_is_not_the_meeting_node(
        self,
    ) -> None:
        tree = SpecStructure(
            root=_combine(
                CombineOp.INTERSECT,
                _combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_ms")),
                _leaf("c_derisi"),
            ),
        )
        assert meeting_operator(tree, ["c_ms", "c_derisi"]) is CombineOp.INTERSECT
