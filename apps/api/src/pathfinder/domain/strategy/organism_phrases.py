"""The organism entries a message states whole, and the classifications that split one."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ConfigDict
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
)
from pathfinder.domain.strategy.words import spelled_words, words_of

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

    def spelled(self, positions: Sequence[int]) -> str:
        """The entry's own words at these positions of the reading."""
        words = spelled_words(self.entry)
        return " ".join(words[k] for k in positions)


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


def _refusal(stated: StatedOrganism, positions: Sequence[int]) -> str:
    return (
        f'The message names the organism "{stated.entry}", one entry of this '
        "site's organism list. Record it whole as the organism constraint; "
        f'"{stated.spelled(positions)}" is part of its name, not a requirement '
        "of its own."
    )


def _truncated(value: str, stated: StatedOrganism) -> str | None:
    """The refusal of an organism value that is a proper prefix of the entry."""
    value_words = tuple(words_of(value))
    size = len(value_words)
    for reading in _readings(stated.entry):
        if 0 < size < len(reading) and reading[:size] == value_words:
            return _refusal(stated, range(size, len(reading)))
    return None


def _held_only_inside(
    words: Sequence[str], stated: Sequence[StatedOrganism]
) -> set[str]:
    """The message words every occurrence of which lies inside a stated entry."""
    inside = {k for s in stated for k in range(s.start, s.end)}
    outside = {word for k, word in enumerate(words) if k not in inside}
    return {words[k] for k in inside} - outside


def _borrowed(
    value: str, held: set[str], stated: Sequence[StatedOrganism]
) -> str | None:
    """The refusal of a value that carries a word only an entry holds.

    A stated entry the value names whole is no borrowing.
    """
    named = stated_organisms(value, [s.entry for s in stated])
    covered = {k for s in named for k in range(s.start, s.end)}
    words = words_of(value)
    borrowed = {w for k, w in enumerate(words) if k not in covered} & held
    for organism in stated:
        positions = [k for k, w in enumerate(organism.reading) if w in borrowed]
        if positions:
            return _refusal(organism, positions)
    return None


def _values(constraint: Constraint) -> list[str]:
    """The values a constraint states: one per term of a combination."""
    value = constraint.requested_value
    if constraint.kind is not ConstraintKind.COMBINATION:
        return [value]
    request = CombinationRequest.parse(value)
    return [value] if request is None else request.terms


def _split(
    constraint: Constraint, held: set[str], stated: Sequence[StatedOrganism]
) -> str | None:
    if constraint.kind is ConstraintKind.ORGANISM:
        value = constraint.requested_value
        return next(
            (r for s in stated if (r := _truncated(value, s)) is not None), None
        )
    return next(
        (
            r
            for value in _values(constraint)
            if (r := _borrowed(value, held, stated)) is not None
        ),
        None,
    )


def organism_split_refusal(
    constraints: Sequence[Constraint], message: str, stated: Sequence[StatedOrganism]
) -> str | None:
    """Why these constraints split an organism entry the message states whole.

    None when every stated entry is recorded whole, and no other requirement
    or combination term carries a word the message holds only inside one.
    """
    held = _held_only_inside(words_of(message), stated)
    return next(
        (r for c in constraints if (r := _split(c, held, stated)) is not None), None
    )
