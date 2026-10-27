"""Where a reference stands in its clause: with no noun after a count it
renders with its noun."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from pathfinder.domain.reference_grammar import (
    A_REFERENCE,
    carries_its_noun,
)
from pathfinder.domain.turn_facts import StepFact

# "both" names two inputs, as in the genes an intersect keeps in both.
_NUMBER_WORDS = (
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
    "twice",
    "times",
    "dozen",
    # A share of a count is a number the facts hold or a difference renders.
    "half",
    "third",
    "quarter",
    "fifth",
    "percent",
)
_A_NUMBER_WORD = re.compile(
    rf"\b(?:[a-z]+-fold|{'|'.join(_NUMBER_WORDS)})\b", re.IGNORECASE
)
_A_WRITTEN_NUMBER = re.compile(
    rf"{_A_NUMBER_WORD.pattern}|(?<![\w:.,-])\d[\d,]*(?:\.\d+)?(?![\w:-]|[.,]\d)",
    re.IGNORECASE,
)
_CLAUSE_END = re.compile(r"[.;:,!?\n]")
_A_WORD = re.compile(r"[A-Za-z][\w'-]*")
_A_COMPOUND = re.compile(r"[a-z]+(?:-[a-z]+)+")
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

type MisplacementKind = Literal["noun_after_count"]


@dataclass(frozen=True)
class Misplacement:
    """A count reference and the noun written after it."""

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


def _noun_after(
    masked: str, end: int, stop: int, nouns: frozenset[str], between: frozenset[str]
) -> int:
    """The end of the count noun that follows a reference, next or after only
    continuation words and compound modifiers, each with one word after it, or -1."""
    tail = masked[end:stop].split(_MASK, 1)[0]
    modified = False
    for word in _A_WORD.finditer(tail):
        said = word.group().casefold()
        if said in nouns:
            return end + word.end()
        compound = _A_COMPOUND.fullmatch(said) is not None
        if not (said in between or compound or modified):
            return -1
        modified = compound
    return -1


def _in_clause(
    prose: str,
    masked: str,
    span: tuple[int, int],
    nouns: frozenset[str],
    between: frozenset[str],
) -> Iterator[Misplacement]:
    start, stop = span
    references = [m for m in A_REFERENCE.finditer(prose) if start <= m.start() < stop]
    for match in references:
        if not carries_its_noun(match):
            continue
        noun_end = _noun_after(masked, match.end(), stop, nouns, between)
        if noun_end >= 0:
            token = prose[match.start() : noun_end]
            yield Misplacement("noun_after_count", token, match.group())


def clause_texts(prose: str) -> list[str]:
    masked = A_REFERENCE.sub(lambda m: _MASK * len(m.group()), prose)
    return [prose[start:stop] for start, stop in _clauses(masked)]


def misplacements(
    prose: str, record_nouns: Sequence[str], steps: Sequence[StepFact] = ()
) -> list[Misplacement]:
    """Each count reference with a count noun after it, next or after only
    continuation words and the words that name the steps."""
    masked = A_REFERENCE.sub(lambda m: _MASK * len(m.group()), prose)
    nouns = _count_nouns(record_nouns)
    texts = (t for s in steps for t in (s.display_name, s.reason))
    named = (w.group().casefold() for t in texts for w in _A_WORD.finditer(t))
    between = _CONTINUATIONS | frozenset(named)
    return [
        found
        for span in _clauses(masked)
        for found in _in_clause(prose, masked, span, nouns, between)
    ]


def written_numbers(text: str) -> list[str]:
    return [found.group() for found in _A_WRITTEN_NUMBER.finditer(text)]


__all__ = ["Misplacement", "clause_texts", "misplacements", "written_numbers"]
