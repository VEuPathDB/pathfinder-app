"""The requirements a thread records as its messages state them."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import NamedTuple

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintSource,
    ReplacedLifecycle,
    new_requirement_id,
)
from pathfinder.domain.strategy.requirement_lifecycle import (
    MANY_VALUED_KINDS,
    RetiredRequirement,
)


def _quoted(constraint: Constraint, messages: Sequence[str]) -> bool:
    quote = constraint.quote.casefold()
    return bool(quote) and any(quote in m.casefold() for m in messages)


def attributed(
    constraints: Iterable[Constraint], messages: Sequence[str]
) -> list[Constraint]:
    """Each stated requirement, marked by whether the researcher's words quote it.

    ``messages`` are the words the researcher wrote or accepted on this thread.
    A requirement whose quote one of them holds is the user's word; any other
    is an assumption: it is surfaced, and it gates nothing.
    """
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
        for stated in [_quoted(constraint, messages)]
    ]


def identified(
    constraints: Iterable[Constraint], recorded: Sequence[Constraint]
) -> list[Constraint]:
    by_value = {(c.kind, c.requested_value): c.id for c in recorded}
    owned = set(by_value.values())
    found: list[Constraint] = []
    for constraint in constraints:
        value = (constraint.kind, constraint.requested_value)
        held = by_value.get(value)
        if held is None and constraint.id in owned:
            held = new_requirement_id()
        kept = (
            constraint
            if held is None or held == constraint.id
            else constraint.model_copy(update={"id": held})
        )
        found.append(kept)
        by_value[value] = kept.id
        owned.add(kept.id)
    return found


class RecordedRequirements(NamedTuple):
    """The live requirements, and each one a newer requirement displaced."""

    live: list[Constraint]
    displaced: list[RetiredRequirement]


def _displaces(new: Constraint, held: Constraint) -> bool:
    """Whether a new requirement takes the place of a held one.

    A kind of one value is displaced by any other value of it, unless the new
    one is stated beside it. A kind of many values adds.
    """
    if new.kind is not held.kind or held.id in {new.id, new.beside}:
        return False
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
    held: Sequence[Constraint], constraints: Iterable[Constraint]
) -> RecordedRequirements:
    """The record with each new requirement added once, and each ``held`` one
    it displaces. Values stated together displace neither, a value stated
    beside a held one adds, and an assumed value never displaces a stated one:
    it is dropped."""
    record = list(held)
    displaced: list[RetiredRequirement] = []
    seen = {c.id for c in record}
    for constraint in constraints:
        if constraint.id in seen or _outranked(constraint, record):
            continue
        replaced = [
            kept for kept in record if kept in held and _displaces(constraint, kept)
        ]
        record = [kept for kept in record if kept not in replaced]
        displaced += [
            RetiredRequirement(
                constraint=kept, lifecycle=ReplacedLifecycle(by=constraint.id)
            )
            for kept in replaced
        ]
        seen.add(constraint.id)
        record.append(constraint)
    return RecordedRequirements(live=record, displaced=displaced)
