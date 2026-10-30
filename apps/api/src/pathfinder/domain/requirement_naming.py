"""Which one requirement of the researcher a text of a check names."""

from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.strategy.constraints import (
    ConstraintSource,
    GroundedConstraint,
    message_states,
)


def _names(text: str, words: str) -> bool:
    """Whether the text carries the words, or the words carry the text."""
    return message_states(text, words) or message_states(words, text)


def requirement_naming(
    text: str, requirements: Sequence[GroundedConstraint]
) -> GroundedConstraint | None:
    """The one requirement of the researcher the text names, by its key.

    A requirement a parameter of a step answers is not the one the text
    misses, so a text that names only those names none. A text that names
    several of the rest, or none, names no one requirement, so the order the
    requirements come in decides nothing.
    """
    named = {
        held.constraint.key: held
        for held in requirements
        if held.constraint.source is ConstraintSource.USER_EXPLICIT
        and _names(text, held.constraint.requested_value)
    }
    missing = [held for held in named.values() if not held.answered_by_a_parameter]
    return missing[0] if len(missing) == 1 else None


def names_a_retired_requirement(
    text: str, requirements: Sequence[GroundedConstraint]
) -> bool:
    """Whether the one requirement the text names is withdrawn or replaced."""
    held = requirement_naming(text, requirements)
    return held is not None and held.retired


__all__ = [
    "names_a_retired_requirement",
    "requirement_naming",
]
