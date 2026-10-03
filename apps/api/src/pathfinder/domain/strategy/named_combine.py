"""A combine the researcher names by its place in the tree, the operators a
message states, and the checks that an edit moves only the combines it states."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from typing import Literal

from pydantic import ConfigDict
from veupathdb.domain.strategy import CombineOp
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.combination_check import (
    CombinationBreach,
    required_operator,
)
from pathfinder.domain.strategy.constraints import CombinationRequest, Constraint
from pathfinder.domain.strategy.operational_spec import (
    SpecStructure,
    StructureNode,
    criteria_under,
)

CombinePosition = Literal["root", "deepest"]

_NOUN = r"(?:combine|combination|join|boolean|operator)"
_PLACED_RE = re.compile(
    rf"\b(?P<root>last|final|top|outer(?:most)?|root)\s+{_NOUN}\b"
    rf"|\b(?P<deepest>first|inner(?:most)?)\s+{_NOUN}\b",
    re.IGNORECASE,
)
_CLAUSE_END_RE = re.compile(r"[,;.!?]")
_OPERATOR_WORDS: dict[CombineOp, re.Pattern[str]] = {
    CombineOp.UNION: re.compile(r"\bunion\b", re.IGNORECASE),
    CombineOp.INTERSECT: re.compile(r"\bintersect(?:ion|s|ed)?\b", re.IGNORECASE),
    CombineOp.MINUS: re.compile(r"\bminus\b", re.IGNORECASE),
}


def stated_operators(message: str) -> frozenset[CombineOp]:
    """The combine operators the message names by an operator word."""
    return frozenset(op for op, word in _OPERATOR_WORDS.items() if word.search(message))


def _stated_operator(text: str) -> CombineOp | None:
    stated = stated_operators(text) & {CombineOp.UNION, CombineOp.INTERSECT}
    return next(iter(stated)) if len(stated) == 1 else None


class NamedCombine(CamelModel):
    """The combine a message names by its place, and the operator it states.

    "last", "final", "top", "outer" and "root" name the root combine; "first"
    and "inner" name the deepest one.
    """

    model_config = ConfigDict(frozen=True)

    position: CombinePosition
    operator: CombineOp

    @classmethod
    def read(cls, message: str) -> NamedCombine | None:
        """The one placed combine the message names with an operator, or None.

        The operator is read in the clause after the placing words. A message
        that places two combines names no single one.
        """
        found = list(_PLACED_RE.finditer(message))
        if len(found) != 1:
            return None
        placed = found[0]
        clause = _CLAUSE_END_RE.split(message[placed.end() :])[0]
        operator = _stated_operator(clause)
        if operator is None:
            return None
        position: CombinePosition = "root" if placed.group("root") else "deepest"
        return cls(position=position, operator=operator)


def _combines(
    node: StructureNode, depth: int = 0
) -> Iterator[tuple[int, StructureNode]]:
    if node.kind == "combine":
        yield depth, node
    for child in node.inputs:
        yield from _combines(child, depth + 1)


def combine_at(
    structure: SpecStructure, position: CombinePosition
) -> StructureNode | None:
    """The shallowest or the deepest combine, or None when two share that depth."""
    found = list(_combines(structure.root))
    if not found:
        return None
    depths = [depth for depth, _ in found]
    wanted = min(depths) if position == "root" else max(depths)
    at = [node for depth, node in found if depth == wanted]
    return at[0] if len(at) == 1 else None


def _operator_moves(
    proposed: SpecStructure, held: SpecStructure
) -> Iterator[tuple[StructureNode, StructureNode]]:
    """Each held combine and the proposed combine that joins the same criteria
    with another operator."""
    proposed_by_members = {
        criteria_under(node): node for _, node in _combines(proposed.root)
    }
    for _, node in _combines(held.root):
        moved = proposed_by_members.get(criteria_under(node))
        if moved is not None and moved.operator is not node.operator:
            yield node, moved


def _moved_combine(
    named: NamedCombine, proposed: SpecStructure, held: SpecStructure
) -> tuple[StructureNode, StructureNode] | None:
    """A combine the held tree has, other than the named one, that the proposed
    tree joins with another operator over the same criteria."""
    held_named = combine_at(held, named.position)
    return next(
        (move for move in _operator_moves(proposed, held) if move[0] is not held_named),
        None,
    )


def combination_operators(combinations: Sequence[Constraint]) -> frozenset[CombineOp]:
    """The combine operators the stated combinations require."""
    return frozenset(
        required_operator(request.operator)
        for c in combinations
        if (request := CombinationRequest.parse(c.requested_value)) is not None
    )


def unstated_operator_move(
    proposed: SpecStructure, held: SpecStructure, stated: frozenset[CombineOp]
) -> tuple[StructureNode, StructureNode] | None:
    """A held combine the proposed tree moves to an operator not in ``stated``,
    as the held node and the proposed node."""
    return next(
        (
            move
            for move in _operator_moves(proposed, held)
            if move[1].operator not in stated
        ),
        None,
    )


def named_combine_breach(
    named: NamedCombine, proposed: SpecStructure, *, held: SpecStructure | None
) -> CombinationBreach | None:
    """How this tree breaks the named combine, or None.

    The named combine carries the stated operator, and every other combine the
    held tree has keeps its operator.
    """
    expression = f"the {named.position} combine {named.operator.value}"
    node = combine_at(proposed, named.position)
    if node is None or node.operator is not named.operator:
        built = "no combine node" if node is None else node.combine_operator.value
        return CombinationBreach(
            required=named.operator,
            expression=expression,
            built=built,
            message=(
                f"the user names the {named.position} combine, which must be "
                f"{named.operator.value}, but the tree joins it at {built}"
            ),
        )
    moved = None if held is None else _moved_combine(named, proposed, held)
    if moved is None:
        return None
    was, now = moved
    members = ", ".join(sorted(criteria_under(was)))
    return CombinationBreach(
        required=was.combine_operator,
        expression=expression,
        built=now.combine_operator.value,
        message=(
            f"the user names only the {named.position} combine, but the tree "
            f"moves the combine over {members} from {was.combine_operator.value} "
            f"to {now.combine_operator.value}"
        ),
    )
