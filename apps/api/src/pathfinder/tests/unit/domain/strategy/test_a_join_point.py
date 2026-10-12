"""A criterion with no step joins the built part of the smallest branch that names it."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.join_point import JoinPoint, branch_step, join_point
from pathfinder.domain.strategy.operational_spec import SpecStructure, StructureNode

from ._builders import (
    combine,
    graph_with,
    leaf,
    spec_joined,
    spec_leaf,
    spec_transform,
    transform,
)

_WAITING = ("w1", "w2", "w3", "w4")


def _structure(root: StructureNode) -> SpecStructure:
    return SpecStructure(root=root)


def _measured() -> SpecStructure:
    return _structure(
        spec_joined(
            CombineOp.INTERSECT,
            spec_leaf("t"),
            spec_joined(CombineOp.UNION, *(spec_leaf(w) for w in _WAITING)),
        )
    )


def _point(anchor: set[str], operator: CombineOp, *, first: bool = False) -> JoinPoint:
    return JoinPoint(frozenset(anchor), operator, comes_first=first)


class TestALeafUnderTheRootCombine:
    def test_a_symmetric_operator_joins_the_built_inputs(self) -> None:
        structure = _structure(
            spec_joined(CombineOp.INTERSECT, spec_leaf("w"), spec_leaf("a"))
        )

        assert join_point(structure, {"a"}, "w") == _point({"a"}, CombineOp.INTERSECT)

    def test_the_last_input_of_a_minus_comes_second(self) -> None:
        structure = _structure(
            spec_joined(CombineOp.MINUS, spec_leaf("a"), spec_leaf("w"))
        )

        assert join_point(structure, {"a"}, "w") == _point({"a"}, CombineOp.MINUS)

    def test_the_first_input_of_a_minus_comes_first(self) -> None:
        structure = _structure(
            spec_joined(CombineOp.MINUS, spec_leaf("w"), spec_leaf("a"))
        )

        assert join_point(structure, {"a"}, "w") == _point(
            {"a"}, CombineOp.MINUS, first=True
        )

    def test_a_symmetric_operator_joins_every_built_input_at_once(self) -> None:
        structure = _structure(
            spec_joined(CombineOp.UNION, spec_leaf("a"), spec_leaf("w"), spec_leaf("b"))
        )

        assert join_point(structure, {"a", "b"}, "w") == _point(
            {"a", "b"}, CombineOp.UNION
        )


class TestTheMeasuredShape:
    """``INTERSECT(t, UNION(w1, w2, w3, w4))`` with only ``t`` built at first."""

    @pytest.mark.parametrize("waiting", _WAITING)
    def test_the_first_export_joins_the_built_step_under_the_root_operator(
        self, waiting: str
    ) -> None:
        assert join_point(_measured(), {"t"}, waiting) == _point(
            {"t"}, CombineOp.INTERSECT
        )

    @pytest.mark.parametrize(
        ("built", "waiting", "anchor"),
        [
            ({"t", "w1"}, "w2", {"w1"}),
            ({"t", "w1", "w2"}, "w3", {"w1", "w2"}),
            ({"t", "w1", "w2", "w3"}, "w4", {"w1", "w2", "w3"}),
            ({"t", "w3"}, "w1", {"w3"}),
            ({"t", "w2", "w4"}, "w3", {"w2", "w4"}),
        ],
    )
    def test_a_later_export_joins_the_built_part_of_the_union(
        self, built: set[str], waiting: str, anchor: set[str]
    ) -> None:
        assert join_point(_measured(), built, waiting) == _point(
            anchor, CombineOp.UNION
        )


class TestABranchWithNoStep:
    def test_it_joins_as_the_second_input_of_the_minus_above_it(self) -> None:
        structure = _structure(
            spec_joined(
                CombineOp.MINUS,
                spec_leaf("a"),
                spec_joined(CombineOp.UNION, spec_leaf("w1"), spec_leaf("w2")),
            )
        )

        assert join_point(structure, {"a"}, "w1") == _point({"a"}, CombineOp.MINUS)

    def test_it_joins_as_the_first_input_of_the_minus_above_it(self) -> None:
        structure = _structure(
            spec_joined(
                CombineOp.MINUS,
                spec_joined(CombineOp.UNION, spec_leaf("w1"), spec_leaf("w2")),
                spec_leaf("a"),
            )
        )

        assert join_point(structure, {"a"}, "w2") == _point(
            {"a"}, CombineOp.MINUS, first=True
        )

    def test_a_transform_above_it_is_passed_through(self) -> None:
        structure = _structure(
            spec_joined(
                CombineOp.INTERSECT,
                spec_leaf("a"),
                spec_transform("c_orthologs", spec_leaf("w")),
            )
        )

        assert join_point(structure, {"a"}, "w") == _point({"a"}, CombineOp.INTERSECT)


class TestAnOrderedOperatorOfManyInputs:
    """``MINUS(x, y, z)`` reads as ``(x MINUS y) MINUS z``."""

    @pytest.mark.parametrize(
        ("order", "point"),
        [
            (("w", "a", "b"), _point({"a"}, CombineOp.MINUS, first=True)),
            (("a", "w", "b"), _point({"a"}, CombineOp.MINUS)),
            (("a", "b", "w"), _point({"a", "b"}, CombineOp.MINUS)),
        ],
    )
    def test_the_step_takes_its_place_in_the_fold(
        self, order: tuple[str, ...], point: JoinPoint
    ) -> None:
        structure = _structure(
            spec_joined(CombineOp.MINUS, *(spec_leaf(c) for c in order))
        )

        assert join_point(structure, {"a", "b"}, "w") == point


def test_a_criterion_beside_no_built_criterion_has_no_join() -> None:
    """Nothing built, a lone leaf, an id the structure lacks, and no structure."""
    assert [
        join_point(_measured(), set(), "w1"),
        join_point(_structure(spec_leaf("w")), {"a"}, "w"),
        join_point(_measured(), {"t"}, "c_absent"),
        join_point(None, {"t"}, "w1"),
    ] == [None, None, None, None]


class TestTheBranchStep:
    def test_one_built_criterion_is_its_own_step(self) -> None:
        graph = graph_with([combine("j1", leaf("t"), leaf("w1"), CombineOp.INTERSECT)])

        assert branch_step(graph, _measured(), {"w1"}) == "w1"

    def test_several_built_criteria_are_the_combine_that_joins_them(self) -> None:
        union = combine("j2", leaf("w1"), leaf("w2"), CombineOp.UNION)
        graph = graph_with([combine("j1", leaf("t"), union, CombineOp.INTERSECT)])

        assert branch_step(graph, _measured(), {"w1", "w2"}) == "j2"

    def test_every_built_criterion_is_the_root(self) -> None:
        graph = graph_with([combine("j1", leaf("t"), leaf("w1"), CombineOp.INTERSECT)])

        assert branch_step(graph, _measured(), {"t", "w1"}) == "j1"

    def test_a_step_the_structure_does_not_name_stays_on_its_branch(self) -> None:
        graph = graph_with([transform("step_unstated", leaf("t"))])

        assert branch_step(graph, _measured(), {"t"}) == "step_unstated"

    def test_criteria_the_strategy_holds_as_no_one_branch_have_none(self) -> None:
        """Joined with another criterion first, and under two roots."""
        joined_with_t_first = graph_with(
            [
                combine(
                    "j2",
                    combine("j1", leaf("t"), leaf("w1"), CombineOp.INTERSECT),
                    leaf("w2"),
                    CombineOp.UNION,
                )
            ]
        )
        two_roots = graph_with([leaf("w1"), leaf("w2")])

        assert [
            branch_step(graph, _measured(), {"w1", "w2"})
            for graph in (joined_with_t_first, two_roots)
        ] == [None, None]
