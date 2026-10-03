"""Which one requirement of the researcher a text of a check names."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from pathfinder.domain.strategy.constraints import (
    ConstraintSource,
    GroundedConstraint,
    message_states,
)
from pathfinder.domain.strategy.words import FILLER_WORDS, words_of


def _names(text: str, words: str) -> bool:
    """Whether the text carries the words, or the words carry the text."""
    return message_states(text, words) or message_states(words, text)


def requirement_naming(
    text: str,
    requirements: Sequence[GroundedConstraint],
    *,
    met: Sequence[str] = (),
) -> GroundedConstraint | None:
    """The one requirement of the researcher the text names, by its key.

    A requirement a ``met`` row names is not the one the text misses. A text
    that names several of the rest, or none, names no one requirement, so the
    order the requirements come in decides nothing.
    """
    named = {
        held.constraint.key: held
        for held in requirements
        if held.constraint.source is ConstraintSource.USER_EXPLICIT
        and _names(text, held.constraint.requested_value)
    }
    missing = [
        held
        for held in named.values()
        if not any(_names(row, held.constraint.requested_value) for row in met)
    ]
    found = missing or list(named.values())
    return found[0] if len(found) == 1 else None


def names_a_requirement(text: str, requirements: Sequence[GroundedConstraint]) -> bool:
    """Whether the text and the value of some requirement carry each other."""
    return any(_names(text, held.constraint.requested_value) for held in requirements)


def names_a_retired_requirement(
    text: str, requirements: Sequence[GroundedConstraint]
) -> bool:
    """Whether the one requirement the text names is withdrawn or replaced."""
    held = requirement_naming(text, requirements)
    return held is not None and held.retired


def _naming(word: str) -> bool:
    return word not in FILLER_WORDS and not word.isdigit()


def named_in_prose(prose: str, text: str) -> bool:
    """Whether the prose names the text: two consecutive naming words of it in
    order, else its naming words, else its whole text verbatim. A number or a
    filler word names nothing."""
    held = words_of(prose)
    wanted = words_of(text)
    pairs = {(a, b) for a, b in pairwise(wanted) if _naming(a) and _naming(b)}
    if pairs:
        return any(pair in pairs for pair in pairwise(held))
    naming = [w for w in wanted if _naming(w)]
    if not naming:
        return text in prose
    return all(w in held for w in naming)


__all__ = [
    "named_in_prose",
    "names_a_requirement",
    "names_a_retired_requirement",
    "requirement_naming",
]
