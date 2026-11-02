"""The requirements a thread no longer holds live, each with its lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from pydantic import ConfigDict, Discriminator
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    ReplacedLifecycle,
    StoredConstraint,
    WithdrawnLifecycle,
)

RetiredLifecycle = Annotated[
    WithdrawnLifecycle | ReplacedLifecycle, Discriminator("state")
]

# The kinds a thread holds any number of values of. Every other kind holds one
# value, so a new value of it replaces the old one.
MANY_VALUED_KINDS = frozenset({ConstraintKind.OTHER, ConstraintKind.COMBINATION})


class RetiredRequirement(CamelModel):
    """A requirement the thread no longer holds live, and why."""

    model_config = ConfigDict(frozen=True)

    constraint: StoredConstraint
    lifecycle: RetiredLifecycle

    def shown_requirements(self) -> list[str]:
        """The requirement each row of this retirement names.

        A withdrawn combination names none: each requirement its criteria
        linked has a row of its own.
        """
        withdrawn = self.lifecycle.state == "withdrawn"
        if withdrawn and self.constraint.kind is ConstraintKind.COMBINATION:
            return []
        return [self.constraint.requested_value]

    def grounded(self) -> GroundedConstraint:
        """The requirement as a check reads it: retired, so it never blocks."""
        return GroundedConstraint(
            constraint=self.constraint,
            status=ConstraintStatus.PROVISIONAL,
            lifecycle=self.lifecycle,
        )


def successor_of(
    requirement: Constraint, stated: Sequence[Constraint]
) -> Constraint | None:
    """The first requirement of the same kind the message states in its place."""
    return next(
        (c for c in stated if c.kind is requirement.kind and c.id != requirement.id),
        None,
    )


def retire(
    held: Sequence[Constraint],
    retired: Sequence[RetiredRequirement],
    gone: Sequence[Constraint],
    *,
    turn_id: str,
    stated: Sequence[Constraint] = (),
    stand_in: Constraint | None = None,
) -> tuple[list[Constraint], list[RetiredRequirement]]:
    """The live and the retired requirements once ``gone`` leaves on this turn:
    replaced by the chosen ``stand_in``, else by a value of its kind the
    message ``stated``, else withdrawn. A requirement the live record does not
    hold retires nothing."""
    ids = {c.id for c in gone}

    def _lifecycle(requirement: Constraint) -> RetiredLifecycle:
        successor = stand_in or successor_of(requirement, stated)
        if successor is None:
            return WithdrawnLifecycle(turn_id=turn_id)
        return ReplacedLifecycle(by=successor.id)

    newly = [
        RetiredRequirement(constraint=c, lifecycle=_lifecycle(c))
        for c in held
        if c.id in ids
    ]
    retired_ids = {r.constraint.id for r in newly}
    return (
        [c for c in held if c.id not in retired_ids],
        [*(r for r in retired if r.constraint.id not in retired_ids), *newly],
    )


def reopened(
    retired: Sequence[RetiredRequirement], live: Sequence[Constraint]
) -> list[RetiredRequirement]:
    """The retired requirements a live one does not restate."""
    stated = {c.id for c in live}
    return [r for r in retired if r.constraint.id not in stated]


def restored(
    retired: Sequence[RetiredRequirement], *, turn_id: str, dropped: Sequence[str]
) -> tuple[list[Constraint], list[RetiredRequirement]]:
    """The requirements a declined message retired, and those it leaves retired.

    A message the researcher said no to takes back its withdrawals, and a
    requirement it replaced by one of the ``dropped`` ids is live again.
    """

    def _taken_back(requirement: RetiredRequirement) -> bool:
        match requirement.lifecycle:
            case WithdrawnLifecycle(turn_id=turn):
                return turn == turn_id
            case ReplacedLifecycle(by=by):
                return by in dropped

    return (
        [r.constraint for r in retired if _taken_back(r)],
        [r for r in retired if not _taken_back(r)],
    )
