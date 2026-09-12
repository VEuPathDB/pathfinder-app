"""Whether a strategy tree combines criteria the way the user stated.

A stated combination names its criteria by their words. This module matches
those words to criteria and reads the operators that join them. One rule says
what a branch brings to a combine: a transform the statement names stands for
its whole input, and any other transform brings what its input brings.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import NamedTuple

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.constraints import (
    CombinationOperator,
    CombinationRequest,
    Constraint,
    ConstraintSource,
    combination_requirements_from,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)

_WORD_RE = re.compile(r"[a-z0-9]+")
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Words that name no evidence. Every WDK gene search carries "genes", so a term
# that overlaps a criterion only there names nothing.
_FILLER_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "by",
        "for",
        "from",
        "gene",
        "genes",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)

_REQUIRED_OPERATOR: dict[CombinationOperator, CombineOp] = {
    "OR": CombineOp.UNION,
    "AND": CombineOp.INTERSECT,
}
_MIN_MEETING_CRITERIA = 2


def required_operator(operator: CombinationOperator) -> CombineOp:
    """The WDK combine operator a stated operator requires."""
    return _REQUIRED_OPERATOR[operator]


def _words(text: str) -> frozenset[str]:
    """The content words of a phrase, with camel-case names split apart."""
    spaced = _CAMEL_BOUNDARY_RE.sub(" ", text)
    return frozenset(_WORD_RE.findall(spaced.lower())) - _FILLER_WORDS


def combination_terms_overlap(first: str, second: str) -> bool:
    """Whether two combination statements talk about the same criteria.

    Two statements overlap when any term of one shares a content word with
    any term of the other. A statement that does not parse overlaps nothing.
    """
    a = CombinationRequest.parse(first)
    b = CombinationRequest.parse(second)
    if a is None or b is None:
        return False
    return any(
        _words(term_a) & _words(term_b) for term_a in a.terms for term_b in b.terms
    )


def _best_match(
    wanted: frozenset[str], words_by_id: Mapping[str, frozenset[str]]
) -> str | None:
    """The criterion sharing the most words with a term.

    A tie names two criteria equally well, so it matches neither.
    """
    ranked = sorted(
        ((len(wanted & words), cid) for cid, words in words_by_id.items()),
        reverse=True,
    )
    overlapping = [entry for entry in ranked if entry[0]]
    if not overlapping:
        return None
    if len(overlapping) > 1 and overlapping[0][0] == overlapping[1][0]:
        return None
    return overlapping[0][1]


def match_terms(
    terms: Sequence[str], criteria: Sequence[Criterion]
) -> dict[str, str] | None:
    """The criterion each term names, or None when the check must abstain.

    A term matches the criterion whose text and search name share the most
    words with it. The terms must name distinct criteria.
    """
    words_by_id = {c.id: _words(f"{c.text} {c.search_name}") for c in criteria}
    matched: dict[str, str] = {}
    for term in terms:
        wanted = _words(term)
        if not wanted:
            return None
        found = _best_match(wanted, words_by_id)
        if found is None:
            return None
        matched[term] = found
    if len(matched) != len(terms):
        return None
    if len(set(matched.values())) != len(matched):
        return None
    return matched


class _Brought(NamedTuple):
    """What a branch carries into the combine above it."""

    named: frozenset[str]
    unnamed: bool


def _brought(node: StructureNode, wanted: frozenset[str]) -> _Brought:
    """The criteria this branch brings, split by whether the statement names them.

    A leaf brings its own criterion. A transform the statement names stands for
    its whole input; any other transform brings what its input brings. A
    combine brings what its inputs bring.
    """
    if node.kind == "combine":
        brought = [_brought(child, wanted) for child in node.inputs]
        return _Brought(
            named=frozenset[str]().union(*(item.named for item in brought)),
            unnamed=any(item.unnamed for item in brought),
        )
    criterion_id = node.criterion_id
    if criterion_id is not None and criterion_id in wanted:
        return _Brought(named=frozenset({criterion_id}), unnamed=False)
    if node.kind == "transform" and node.inputs:
        return _brought(node.inputs[0], wanted)
    return _Brought(named=frozenset[str](), unnamed=True)


def _meeting_node(node: StructureNode, wanted: frozenset[str]) -> StructureNode | None:
    """The deepest node that brings every wanted criterion, or None.

    Distinct ids, not occurrences: a duplicated leaf must not stand in for a
    criterion that sits elsewhere in the tree.
    """
    if not wanted <= _brought(node, wanted).named:
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
    that combines nothing. A transform the statement does not name is
    transparent: the criteria under it still meet at the combine above.
    """
    node = _meeting_combine(structure, criterion_ids)
    return None if node is None else node.operator


def _split_operator(
    node: StructureNode, wanted: frozenset[str], required: CombineOp
) -> CombineOp | None:
    """The first operator in this subtree that joins wanted criteria wrongly.

    A combine is constrained when every criterion it brings has a name in the
    statement. One that also brings an unnamed criterion answers a question of
    its own, so it carries any operator.
    """
    for child in node.inputs:
        found = _split_operator(child, wanted, required)
        if found is not None:
            return found
    operator = node.operator
    if operator is None or operator is required:
        return None
    held = _brought(node, wanted)
    if held.unnamed or len(held.named) < _MIN_MEETING_CRITERIA:
        return None
    return operator


def combination_violation(
    request: CombinationRequest,
    matched_ids: Collection[str],
    structure: SpecStructure,
) -> str | None:
    """Why this tree does not state the requested combination, or None.

    Every combine that joins two or more of the named criteria and nothing
    else carries the stated operator, at any depth under the meeting node.
    """
    required = required_operator(request.operator)
    meeting = _meeting_combine(structure, matched_ids)
    if meeting is None or meeting.operator is not required:
        found = None if meeting is None else meeting.operator
        joined = "no combine node" if found is None else found.value
        return (
            f"the user requires {request.expression!r}: those criteria must meet "
            f"at {required.value}, but the tree joins them at {joined}"
        )
    split = _split_operator(meeting, frozenset(matched_ids), required)
    if split is None:
        return None
    return (
        f"the user requires {request.expression!r}: every combine over those "
        f"criteria must be {required.value}, but the tree joins two of them "
        f"at {split.value}"
    )


class CombinationBreach(NamedTuple):
    """A stated combination the tree does not honor."""

    required: CombineOp
    message: str


def first_combination_violation(
    requirements: Iterable[Constraint],
    criteria: Sequence[Criterion],
    structure: SpecStructure,
) -> CombinationBreach | None:
    """The first combination the user stated that this tree contradicts, or None.

    Only a user statement gates a tree: a value the assistant recommended is a
    hint until the user states it. The check abstains on a requirement it
    cannot read: one that states no single operator, or whose terms name no
    distinct criteria of this spec.
    """
    for requirement in combination_requirements_from(list(requirements)):
        if requirement.source is not ConstraintSource.USER_EXPLICIT:
            continue
        request = CombinationRequest.parse(requirement.requested_value)
        if request is None:
            continue
        matched = match_terms(request.terms, criteria)
        if matched is None:
            continue
        message = combination_violation(request, matched.values(), structure)
        if message is not None:
            return CombinationBreach(
                required=required_operator(request.operator),
                message=message,
            )
    return None
