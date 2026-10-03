"""The shape of the references a reply writes in place of a fact, and the
brackets that attempt a reference and are none."""

from __future__ import annotations

import re
from collections.abc import Iterator

# The references that name a fact after a colon, and those that are one word.
REFERENCE_KINDS = (
    "count",
    "before",
    "diff",
    "value",
    "source",
    "compare",
    "record",
    "last_change",
)
BARE_REFERENCES = ("root_before", "root", "url")
A_REFERENCE = re.compile(
    rf"\[(?:(?P<kind>{'|'.join(REFERENCE_KINDS)}):"
    rf"(?P<body>[^\[\]\n]+)|(?P<bare>{'|'.join(BARE_REFERENCES)}))\]"
)
# A bracket group that opens with a reference's name is a reference attempt.
_NAMES_A_REFERENCE = re.compile(
    rf"\s*(?:{'|'.join((*BARE_REFERENCES, *REFERENCE_KINDS))})\b", re.IGNORECASE
)
# The references that render a count with the record noun.
COUNTED_REFERENCES = frozenset(
    {"root", "root_before", "count", "before", "diff", "compare", "last_change"}
)


def reference_kind(match: re.Match[str]) -> str:
    """The kind of one match of ``A_REFERENCE``."""
    return match.group("bare") or match.group("kind")


def reference_and_its_noun(noun: str) -> re.Pattern[str]:
    """A reference, and the record noun written after it in any case, with the
    spaces, hyphens or colons between them."""
    return re.compile(
        rf"{A_REFERENCE.pattern}(?P<noun>(?i:[ \t:-]*\b{re.escape(noun)}s?\b))?"
    )


def _closing(prose: str, start: int) -> int:
    """The index of the bracket that closes the one at ``start`` on its line,
    or -1."""
    depth = 0
    for index in range(start, len(prose)):
        match prose[index]:
            case "\n":
                return -1
            case "[":
                depth += 1
            case "]":
                depth -= 1
                if depth == 0:
                    return index
    return -1


def malformed_brackets(prose: str) -> Iterator[str]:
    """Each bracket outside a reference that nests, opens with a reference's
    name, or is never closed. A bracketed word that names no reference is prose."""
    index = 0
    while index < len(prose):
        reference = A_REFERENCE.match(prose, index)
        if reference is not None:
            index = reference.end()
            continue
        if prose[index] == "]":
            yield prose[index]
        if prose[index] != "[":
            index += 1
            continue
        end = _closing(prose, index)
        if end < 0:
            yield prose[index:].split(maxsplit=1)[0]
            index += 1
            continue
        group = prose[index : end + 1]
        inner = group[1:-1]
        if "[" in inner or _NAMES_A_REFERENCE.match(inner):
            yield group
        index = end + 1


__all__ = [
    "A_REFERENCE",
    "BARE_REFERENCES",
    "COUNTED_REFERENCES",
    "REFERENCE_KINDS",
    "malformed_brackets",
    "reference_and_its_noun",
    "reference_kind",
]
