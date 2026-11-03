"""The organism entries a message states whole, and the entry an organism
reading completes to among them."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.words import words_of

# A binomial is a genus and a species epithet, and only a genus abbreviates.
_BINOMIAL_WORDS = 2


class OrganismSpan(CamelModel):
    """One organism entry the message states, and the message words it covers."""

    model_config = ConfigDict(frozen=True)

    entry: str
    start: int
    end: int
    reading: tuple[str, ...]
    """The entry's words as the message holds them, the genus possibly an initial."""


def _readings(entry: str) -> list[tuple[str, ...]]:
    """The entry's words, and the same words with the genus as its initial."""
    words = tuple(words_of(entry))
    if len(words) < _BINOMIAL_WORDS:
        return [words]
    return [words, (words[0][0], *words[1:])]


def _longest_at(
    words: Sequence[str], start: int, readings: Sequence[tuple[str, tuple[str, ...]]]
) -> OrganismSpan | None:
    found: OrganismSpan | None = None
    for entry, reading in readings:
        end = start + len(reading)
        if tuple(words[start:end]) != reading:
            continue
        if found is None or end > found.end:
            found = OrganismSpan(entry=entry, start=start, end=end, reading=reading)
    return found


def stated_organisms(message: str, vocabulary: Sequence[str]) -> list[OrganismSpan]:
    """Every vocabulary entry the message states whole, left to right.

    The longest entry wins at a position, and a word belongs to one entry.
    """
    words = words_of(message)
    readings = [(entry, r) for entry in vocabulary for r in _readings(entry)]
    stated: list[OrganismSpan] = []
    start = 0
    while start < len(words):
        found = _longest_at(words, start, readings)
        if found is None:
            start += 1
            continue
        stated.append(found)
        start = found.end
    return stated


def _begins(words: tuple[str, ...], entry: str) -> bool:
    return bool(words) and any(
        reading[: len(words)] == words for reading in _readings(entry)
    )


def completed_entry(words: str, message: str, vocabulary: Sequence[str]) -> str | None:
    named = tuple(words_of(words))
    begun = {
        span.entry
        for span in stated_organisms(message, vocabulary)
        if _begins(named, span.entry)
    }
    return next(iter(begun)) if len(begun) == 1 else None
