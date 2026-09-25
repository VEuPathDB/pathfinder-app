"""Each leaf of an offered tree is read by dropping it and evaluating the rest.

The sets are small enough to check by hand: six positives, four negatives.
"""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.domain.separation import LeafContribution, OfferedLeaf, ablate
from pathfinder.domain.strategy.operational_spec import StructureNode

_POSITIVES = ["P1", "P2", "P3", "P4", "P5", "P6"]
_NEGATIVES = ["N1", "N2", "N3", "N4"]


def _leaf(criterion_id: str, recovered: list[str], admitted: list[str]) -> OfferedLeaf:
    return OfferedLeaf(
        criterion_id=criterion_id,
        display_name=f"search {criterion_id}",
        controls=ControlTestEvidence(
            tested_label=f"search {criterion_id}",
            positive=ControlSetEvidence(
                returned=recovered,
                not_returned=[p for p in _POSITIVES if p not in recovered],
            ),
            negative=ControlSetEvidence(
                returned=admitted,
                not_returned=[n for n in _NEGATIVES if n not in admitted],
            ),
        ),
    )


_A = _leaf("a", ["P1", "P2", "P3"], ["N1", "N2"])
_B = _leaf("b", ["P3", "P4"], ["N2", "N3"])
_C = _leaf("c", [], ["N1", "N3"])
_D = _leaf("d", ["P1", "P2", "P3", "P5"], ["N2", "N4"])


def _node(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _combine(
    operator: CombineOp, left: StructureNode, right: StructureNode
) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=[left, right])


def _by_leaf(found: list[LeafContribution]) -> dict[str, tuple[list[str], ...]]:
    return {
        c.criterion_id: (c.only_recovers, c.holds_back, c.only_excludes, c.brings_in)
        for c in found
    }


def test_a_subtracted_leaf_is_the_negatives_it_alone_removes() -> None:
    tree = _combine(
        CombineOp.MINUS, _combine(CombineOp.UNION, _node("a"), _node("b")), _node("c")
    )

    found = ablate(tree, [_A, _B, _C])

    assert _by_leaf(found) == {
        "a": (["P1", "P2"], [], [], []),
        "b": (["P4"], [], [], []),
        "c": ([], [], ["N1", "N3"], []),
    }
    assert [c.line for c in found] == [
        "without it: -2 positives, 0 negatives",
        "without it: -1 positives, 0 negatives",
        "without it: 0 positives, +2 negatives",
    ]


def test_a_united_leaf_brings_its_own_negatives_in() -> None:
    found = ablate(_combine(CombineOp.UNION, _node("a"), _node("b")), [_A, _B])

    assert _by_leaf(found)["b"] == (["P4"], [], [], ["N3"])
    assert found[1].line == "without it: -1 positives, -1 negatives"


def test_an_intersected_leaf_can_hold_back_a_positive() -> None:
    found = ablate(_combine(CombineOp.INTERSECT, _node("a"), _node("d")), [_A, _D])

    assert _by_leaf(found) == {
        "a": ([], ["P5"], ["N4"], []),
        "d": ([], [], ["N1"], []),
    }
    assert [(c.positive_change, c.negative_change) for c in found] == [(1, 1), (0, 1)]


def test_the_only_leaf_carries_everything_the_tree_returns() -> None:
    (only,) = ablate(_node("a"), [_A])

    assert (only.only_recovers, only.brings_in) == (["P1", "P2", "P3"], ["N1", "N2"])
    assert only.line == "without it: -3 positives, -2 negatives"
