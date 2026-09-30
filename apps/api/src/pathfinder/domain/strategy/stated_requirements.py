"""The requirements a thread records as its messages state them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import NamedTuple

from pathfinder.domain.strategy.combination_check import combination_terms_overlap
from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    adds_an_alternative,
    message_states,
    message_states_constraint,
)
from pathfinder.domain.strategy.requirement_lifecycle import RetiredRequirement


def _added_as_an_alternative(constraint: Constraint, messages: Sequence[str]) -> bool:
    """Whether the newest message adds an OR arm to terms the messages carry."""
    request = (
        CombinationRequest.parse(constraint.requested_value)
        if constraint.kind is ConstraintKind.COMBINATION
        else None
    )
    return (
        request is not None
        and request.operator == "OR"
        and bool(messages)
        and adds_an_alternative(messages[0])
        and all(any(message_states(m, t) for m in messages) for t in request.terms)
    )


def attributed(
    constraints: Iterable[Constraint],
    messages: Sequence[str],
    held: Sequence[Constraint],
) -> list[Constraint]:
    """Each stated requirement, marked by who the researcher's words say stated it.

    ``messages`` are the words the researcher wrote or accepted on this thread,
    the newest first. A value one of them carries is the user's word. A value only the
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
            any(message_states_constraint(m, constraint) for m in messages if m)
            or _added_as_an_alternative(constraint, messages)
            or constraint.requested_value.casefold() in theirs
        ]
    ]


class RecordedRequirements(NamedTuple):
    """The live requirements, and each one a newer requirement displaced."""

    live: list[Constraint]
    displaced: list[RetiredRequirement]


def with_requirements(
    held: Sequence[Constraint], constraints: Iterable[Constraint]
) -> RecordedRequirements:
    """The record with each new requirement added, a restated one added once.

    A new combination over the same criteria displaces the old one, which
    retires as replaced by the new one's key."""
    record = list(held)
    displaced: list[RetiredRequirement] = []
    seen = {(c.kind, c.requested_value) for c in record}
    for constraint in constraints:
        key = (constraint.kind, constraint.requested_value)
        if key in seen:
            continue
        if constraint.kind is ConstraintKind.COMBINATION:
            replaced = [
                kept
                for kept in record
                if kept.kind is ConstraintKind.COMBINATION
                and combination_terms_overlap(
                    kept.requested_value, constraint.requested_value
                )
            ]
            record = [kept for kept in record if kept not in replaced]
            displaced += [
                RetiredRequirement(
                    constraint=kept, lifecycle=ReplacedLifecycle(by=constraint.key)
                )
                for kept in replaced
            ]
        seen.add(key)
        record.append(constraint)
    return RecordedRequirements(live=record, displaced=displaced)
