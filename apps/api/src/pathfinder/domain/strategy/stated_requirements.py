"""The requirements a thread records as its messages state them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pathfinder.domain.strategy.combination_check import combination_terms_overlap
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    message_states_constraint,
)


def attributed(
    constraints: Iterable[Constraint], message: str, held: Sequence[Constraint]
) -> list[Constraint]:
    """Each stated requirement, marked by who the message says stated it.

    A value the message carries is the user's word. A value only the
    classifier composed is an assumption: it is surfaced, and it gates
    nothing. A value the user already stated on this thread stays theirs.
    """
    theirs = {
        c.requested_value.casefold()
        for c in held
        if c.source is ConstraintSource.USER_EXPLICIT
    }
    return [
        constraint.model_copy(
            update={
                "source": ConstraintSource.USER_EXPLICIT
                if stated
                else ConstraintSource.ASSUMED,
                "hard": constraint.hard and stated,
            },
        )
        for constraint in constraints
        for stated in [
            message_states_constraint(message, constraint)
            or constraint.requested_value.casefold() in theirs
        ]
    ]


def with_requirements(
    held: Sequence[Constraint], constraints: Iterable[Constraint]
) -> list[Constraint]:
    """The record with each requirement it does not hold already added.

    Two requirements are the same when they hold the same value on the same
    dimension, so a restated one is not a second requirement. A new
    combination over the same criteria replaces the old one, so a changed
    mind never leaves two statements no tree can satisfy together.
    """
    record = list(held)
    seen = {(c.kind, c.requested_value) for c in record}
    for constraint in constraints:
        key = (constraint.kind, constraint.requested_value)
        if key in seen:
            continue
        if constraint.kind is ConstraintKind.COMBINATION:
            record = [
                kept
                for kept in record
                if kept.kind is not ConstraintKind.COMBINATION
                or not combination_terms_overlap(
                    kept.requested_value, constraint.requested_value
                )
            ]
        seen.add(key)
        record.append(constraint)
    return record
