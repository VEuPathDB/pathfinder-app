"""The organism entries a message states whole, and the completion of an
organism value that records only the start of one."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.words import words_of

# A binomial is a genus and a species epithet, and only a genus abbreviates.
_BINOMIAL_WORDS = 2


class StatedOrganism(CamelModel):
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
) -> StatedOrganism | None:
    found: StatedOrganism | None = None
    for entry, reading in readings:
        end = start + len(reading)
        if tuple(words[start:end]) != reading:
            continue
        if found is None or end > found.end:
            found = StatedOrganism(entry=entry, start=start, end=end, reading=reading)
    return found


def stated_organisms(message: str, vocabulary: Sequence[str]) -> list[StatedOrganism]:
    """Every vocabulary entry the message states whole, left to right.

    The longest entry wins at a position, and a word belongs to one entry.
    """
    words = words_of(message)
    readings = [(entry, r) for entry in vocabulary for r in _readings(entry)]
    stated: list[StatedOrganism] = []
    start = 0
    while start < len(words):
        found = _longest_at(words, start, readings)
        if found is None:
            start += 1
            continue
        stated.append(found)
        start = found.end
    return stated


def completed_organism(value: str, stated: StatedOrganism) -> str | None:
    """The whole entry an organism value is a proper prefix of, or None."""
    value_words = tuple(words_of(value))
    size = len(value_words)
    for reading in _readings(stated.entry):
        if 0 < size < len(reading) and reading[:size] == value_words:
            return stated.entry
    return None


def complete_organisms(
    constraints: Sequence[Constraint], message: str, vocabulary: Sequence[str]
) -> tuple[list[Constraint], list[str]]:
    """The constraints with each organism value that begins an entry the
    message states whole recorded as that entry, and one note per correction."""
    stated = stated_organisms(message, vocabulary)
    completed: list[Constraint] = []
    notes: list[str] = []
    for constraint in constraints:
        whole = None
        if constraint.kind is ConstraintKind.ORGANISM:
            value = constraint.requested_value
            whole = next(
                (w for s in stated if (w := completed_organism(value, s)) is not None),
                None,
            )
        if whole is None:
            completed.append(constraint)
            continue
        completed.append(constraint.model_copy(update={"requested_value": whole}))
        notes.append(f'organism recorded as "{whole}"')
    return completed, notes
