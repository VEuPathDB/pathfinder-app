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
    message_states,
)
from pathfinder.domain.strategy.message_reading import (
    adds_an_alternative,
    message_states_constraint,
)
from pathfinder.domain.strategy.requirement_lifecycle import (
    MANY_VALUED_KINDS,
    RetiredRequirement,
)


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


def _displaces(new: Constraint, held: Constraint) -> bool:
    """Whether a new requirement takes the place of a held one.

    A new combination displaces one over the same criteria. A kind of one
    value is displaced by any other value of it. A kind of many values adds.
    """
    if new.kind is not held.kind or new.key == held.key:
        return False
    if new.kind is ConstraintKind.COMBINATION:
        return combination_terms_overlap(held.requested_value, new.requested_value)
    return new.kind not in MANY_VALUED_KINDS


def _outranked(new: Constraint, record: Sequence[Constraint]) -> bool:
    """Whether an assumed value meets a stated value of its single-valued kind."""
    return (
        new.source is ConstraintSource.ASSUMED
        and new.kind not in MANY_VALUED_KINDS
        and any(
            c.kind is new.kind and c.source is ConstraintSource.USER_EXPLICIT
            for c in record
        )
    )


def with_requirements(
    held: Sequence[Constraint],
    constraints: Iterable[Constraint],
    *,
    adds_alternatives: bool = False,
) -> RecordedRequirements:
    """The record with each new requirement added once, and each ``held`` one
    it displaces. Values stated together displace neither, a message that
    ``adds_alternatives`` adds beside, and an assumed value never displaces a
    stated one: it is dropped."""
    record = list(held)
    displaced: list[RetiredRequirement] = []
    seen = {c.key for c in record}
    for constraint in constraints:
        if constraint.key in seen or _outranked(constraint, record):
            continue
        replaced = [
            kept
            for kept in record
            if kept in held
            and _displaces(constraint, kept)
            and not (adds_alternatives and kept.kind is not ConstraintKind.COMBINATION)
        ]
        record = [kept for kept in record if kept not in replaced]
        displaced += [
            RetiredRequirement(
                constraint=kept, lifecycle=ReplacedLifecycle(by=constraint.key)
            )
            for kept in replaced
        ]
        seen.add(constraint.key)
        record.append(constraint)
    return RecordedRequirements(live=record, displaced=displaced)
