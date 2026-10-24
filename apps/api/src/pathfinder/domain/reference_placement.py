"""Where a reference stands in its clause: in place of the number it renders,
and with no noun after a count it renders with its noun."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from pathfinder.domain.reference_grammar import (
    A_REFERENCE,
    COUNTED_REFERENCES,
    reference_kind,
)
from pathfinder.domain.strategy.words import numeral

_CARDINALS = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
)
# A share of a count is a number the facts hold or a difference renders.
_SHARES = ("twice", "half", "third", "quarter", "fifth", "percent")
_A_NUMBER_WORD = re.compile(
    rf"\b(?:[a-z]+-fold|{'|'.join((*_CARDINALS, *_SHARES))})\b", re.IGNORECASE
)
_A_RENDERED_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

type Rendered = Callable[[re.Match[str]], str | None]
# The references whose clause writes no number word.
_IN_PLACE_OF_A_NUMBER = frozenset(
    {"value", "count", "before", "diff", "root", "root_before", "last_change"}
)
_CLAUSE_END = re.compile(r"[.;:,!?\n]")
_A_WORD = re.compile(r"[A-Za-z][\w'-]*")
# The words that may stand between a count reference and the noun it repeats.
_CONTINUATIONS = frozenset(
    {
        "more",
        "fewer",
        "less",
        "additional",
        "extra",
        "further",
        "matching",
        "such",
        "other",
    }
)
_MASK = "\0"

type MisplacementKind = Literal["number_word", "noun_after_count"]


@dataclass(frozen=True)
class Misplacement:
    """A clause that spells the number a reference renders, or a count
    reference and the noun written after it."""

    kind: MisplacementKind
    token: str
    reference: str


def _count_nouns(record_nouns: Sequence[str]) -> frozenset[str]:
    """The words that count records: gene, record and the nouns the facts count in."""
    heads = {(noun.split() or ["gene"])[-1].casefold() for noun in record_nouns}
    return frozenset(
        {"gene", "genes", "record", "records", *heads, *(f"{h}s" for h in heads)}
    )


def _clauses(masked: str) -> Iterator[tuple[int, int]]:
    start = 0
    for end in _CLAUSE_END.finditer(masked):
        yield start, end.start()
        start = end.end()
    yield start, len(masked)


def _noun_after(masked: str, end: int, stop: int, nouns: frozenset[str]) -> int:
    """The end of the count noun that follows a reference, next or after only
    continuation words, or -1."""
    tail = masked[end:stop].split(_MASK, 1)[0]
    for word in _A_WORD.finditer(tail):
        said = word.group().casefold()
        if said in nouns:
            return end + word.end()
        if said not in _CONTINUATIONS:
            return -1
    return -1


def _numbers(text: str | None) -> frozenset[float]:
    found = _A_RENDERED_NUMBER.findall(text or "")
    return frozenset(float(number.replace(",", "")) for number in found)


def _spells(word: str, rendered: frozenset[float]) -> bool:
    said = word.casefold()
    if said not in _CARDINALS:
        return True
    return float(numeral(said)) in rendered


def _in_clause(
    prose: str,
    masked: str,
    span: tuple[int, int],
    nouns: frozenset[str],
    rendered: Rendered,
) -> Iterator[Misplacement]:
    start, stop = span
    references = [m for m in A_REFERENCE.finditer(prose) if start <= m.start() < stop]
    numbered = [m for m in references if reference_kind(m) in _IN_PLACE_OF_A_NUMBER]
    shown = frozenset(n for m in numbered for n in _numbers(rendered(m)))
    words = (m.group() for m in _A_NUMBER_WORD.finditer(masked, start, stop))
    if numbered and any(_spells(word, shown) for word in words):
        clause = prose[start:stop].strip()
        yield Misplacement("number_word", clause, numbered[0].group())
    for match in references:
        if reference_kind(match) not in COUNTED_REFERENCES:
            continue
        noun_end = _noun_after(masked, match.end(), stop, nouns)
        if noun_end >= 0:
            token = prose[match.start() : noun_end]
            yield Misplacement("noun_after_count", token, match.group())


def misplacements(
    prose: str, record_nouns: Sequence[str], rendered: Rendered
) -> list[Misplacement]:
    """Each clause that spells a number its count or value reference renders,
    or a share of it, and each count reference with a count noun after it."""
    masked = A_REFERENCE.sub(lambda m: _MASK * len(m.group()), prose)
    nouns = _count_nouns(record_nouns)
    return [
        found
        for span in _clauses(masked)
        for found in _in_clause(prose, masked, span, nouns, rendered)
    ]


__all__ = ["Misplacement", "misplacements"]
