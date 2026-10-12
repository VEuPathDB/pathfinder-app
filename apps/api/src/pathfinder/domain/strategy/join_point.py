"""Where a criterion with no step joins the steps the strategy holds."""

from __future__ import annotations

from collections.abc import Collection
from typing import NamedTuple

from veupathdb.domain.strategy import CombineOp, subtree_ids

from pathfinder.domain.strategy.operational_spec import (
    SpecStructure,
    StructureNode,
    criteria_under,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph

__all__ = ["JoinPoint", "branch_step", "join_point"]

_SYMMETRIC = frozenset({CombineOp.INTERSECT, CombineOp.UNION})


class JoinPoint(NamedTuple):
    """The built criteria a new step joins, the operator, and its side.

    ``anchor`` is one branch of the strategy. ``comes_first`` makes the new
    step the first input, which an operator that reads its inputs in order needs.
    """

    anchor: frozenset[str]
    operator: CombineOp
    comes_first: bool


def join_point(
    structure: SpecStructure | None, built: Collection[str], criterion_id: str
) -> JoinPoint | None:
    """Where a step for this criterion joins the criteria that have a step.

    The join is at the lowest combine above the criterion that names a built
    criterion, in that combine's input order. None when no combine does.
    """
    if structure is None:
        return None
    return _join_under(structure.root, frozenset(built), criterion_id)


def _join_under(
    node: StructureNode, built: frozenset[str], criterion_id: str
) -> JoinPoint | None:
    side = next(
        (
            index
            for index, child in enumerate(node.inputs)
            if criterion_id in criteria_under(child)
        ),
        None,
    )
    if side is None:
        return None
    lower = _join_under(node.inputs[side], built, criterion_id)
    if lower is not None or node.kind != "combine":
        return lower
    before = [criteria_under(child) & built for child in node.inputs[:side]]
    after = [criteria_under(child) & built for child in node.inputs[side + 1 :]]
    operator = node.combine_operator
    if operator in _SYMMETRIC:
        anchor, comes_first = frozenset[str]().union(*before, *after), False
    elif any(before):
        anchor, comes_first = frozenset[str]().union(*before), False
    else:
        anchor, comes_first = next(filter(None, after), frozenset[str]()), True
    return JoinPoint(anchor, operator, comes_first) if anchor else None


def branch_step(
    graph: StrategyGraph, structure: SpecStructure | None, anchor: Collection[str]
) -> str | None:
    """The top step of the branch that holds these criteria and no other one.

    None when the strategy joins them with another criterion of the structure
    first, or holds them under no one step.
    """
    named = structure_criteria(structure)
    wanted = frozenset(anchor)
    branches = [
        step_id
        for step_id in graph.steps
        if named.intersection(subtree_ids(step_id, graph.steps)) == wanted
    ]
    return max(branches, key=graph.subtree_size, default=None)
