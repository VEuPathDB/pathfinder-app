"""Where a strategy tree joins criteria: the combine they meet at, and whether
a transform or an exclusion stands over them. Only a filter and a seed are
members of a combine: a transform stands on the path to the root, and an
exclusion is subtracted from a branch.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import NamedTuple

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import (
    SpecStructure,
    StructureNode,
    criteria_under,
)

_MIN_MEETING_CRITERIA = 2


def _nodes(node: StructureNode) -> Iterable[StructureNode]:
    yield node
    for child in node.inputs:
        yield from _nodes(child)


def transform_stands_over(
    structure: SpecStructure, transform_id: str, criterion_ids: Collection[str]
) -> bool:
    """Whether the transform is on the path from one of these criteria to the root."""
    wanted = frozenset(criterion_ids)
    return any(
        node.kind == "transform"
        and node.criterion_id == transform_id
        and bool(criteria_under(node) & wanted)
        for node in _nodes(structure.root)
    )


def _subtracted_side(node: StructureNode) -> int | None:
    """The input slot a difference removes, or None when it removes none."""
    match node.operator:
        case CombineOp.MINUS | CombineOp.LONLY:
            return 1
        case CombineOp.RMINUS | CombineOp.RONLY:
            return 0
        case _:
            return None


def exclusion_stands_over(
    structure: SpecStructure, exclude_id: str, criterion_ids: Collection[str]
) -> bool:
    """Whether this criterion is subtracted from a branch holding these criteria."""
    wanted = frozenset(criterion_ids)
    for node in _nodes(structure.root):
        side = _subtracted_side(node)
        if side is None:
            continue
        removed = criteria_under(node.inputs[side])
        kept = criteria_under(node.inputs[1 - side])
        if exclude_id in removed and wanted <= kept:
            return True
    return False


def _brought(node: StructureNode, wanted: frozenset[str]) -> frozenset[str]:
    """The wanted criteria this branch brings into the combine above it.

    A leaf brings its own criterion. A wanted transform stands for its whole
    input; any other transform brings what its input brings. A combine brings
    what its inputs bring.
    """
    if node.kind == "combine":
        return frozenset[str]().union(*(_brought(c, wanted) for c in node.inputs))
    criterion_id = node.criterion_id
    if criterion_id is not None and criterion_id in wanted:
        return frozenset({criterion_id})
    if node.kind == "transform":
        return _brought(node.inputs[0], wanted)
    return frozenset[str]()


def _meeting_node(node: StructureNode, wanted: frozenset[str]) -> StructureNode | None:
    """The deepest node that brings every wanted criterion, or None.

    Distinct ids, not occurrences: a duplicated leaf must not stand in for a
    criterion that sits elsewhere in the tree.
    """
    if not wanted <= _brought(node, wanted):
        return None
    for child in node.inputs:
        deeper = _meeting_node(child, wanted)
        if deeper is not None:
            return deeper
    return node


def _meeting_combine(
    structure: SpecStructure, criterion_ids: Collection[str]
) -> StructureNode | None:
    """The combine node where these criteria meet, or None."""
    wanted = frozenset(criterion_ids)
    if len(wanted) < _MIN_MEETING_CRITERIA:
        return None
    node = _meeting_node(structure.root, wanted)
    if node is None or node.kind != "combine":
        return None
    return node


def meeting_operator(
    structure: SpecStructure, criterion_ids: Collection[str]
) -> CombineOp | None:
    """The operator of the node where these criteria meet.

    None when one of them is absent from the tree, or when they meet at a node
    that combines nothing. A transform that is not one of them is
    transparent: the criteria under it still meet at the combine above.
    """
    node = _meeting_combine(structure, criterion_ids)
    return None if node is None else node.operator


class CombinationBreach(NamedTuple):
    """A combine the researcher names that the tree does not honor, and the
    operator it joins the criteria with instead."""

    required: CombineOp
    expression: str
    built: str
    message: str
