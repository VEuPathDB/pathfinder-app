"""The requirements a thread no longer holds live, each with its lifecycle."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated

from pydantic import ConfigDict, Discriminator, Field
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
    GroundedConstraint,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)

RetiredLifecycle = Annotated[
    WithdrawnLifecycle | ReplacedLifecycle, Discriminator("state")
]


class RequirementWithdrawal(CamelModel):
    """A held requirement a message takes back, and what replaces it."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(
        min_length=1,
        description=(
            "The key of the requirement the message takes back, as the ledger "
            "lists it: '<dimension>:<requested value>'."
        ),
    )
    replaced_by: str = Field(
        default="",
        description=(
            "The key of the requirement this same message states in its place. "
            "Empty when the message only removes it."
        ),
    )


class RetiredRequirement(CamelModel):
    """A requirement the thread no longer holds live, and why."""

    model_config = ConfigDict(frozen=True)

    constraint: Constraint
    lifecycle: RetiredLifecycle

    def grounded(self) -> GroundedConstraint:
        """The requirement as a check reads it: retired, so it never blocks."""
        return GroundedConstraint(
            constraint=self.constraint,
            status=ConstraintStatus.PROVISIONAL,
            lifecycle=self.lifecycle,
        )


def retire(
    held: Sequence[Constraint],
    retired: Sequence[RetiredRequirement],
    withdrawals: Sequence[RequirementWithdrawal],
    *,
    turn_id: str,
) -> tuple[list[Constraint], list[RetiredRequirement]]:
    """The live requirements and the retired ones once the withdrawals apply.

    A requirement with a successor is replaced; one without is withdrawn on
    this turn. A key the live record does not hold retires nothing.
    """
    by_key = {w.key: w for w in withdrawals}
    newly = [
        RetiredRequirement(
            constraint=c,
            lifecycle=(
                ReplacedLifecycle(by=w.replaced_by)
                if w.replaced_by
                else WithdrawnLifecycle(turn_id=turn_id)
            ),
        )
        for c in held
        if (w := by_key.get(c.key)) is not None
    ]
    retired_keys = {r.constraint.key for r in newly}
    return (
        [c for c in held if c.key not in retired_keys],
        [*(r for r in retired if r.constraint.key not in retired_keys), *newly],
    )


def reopened(
    retired: Sequence[RetiredRequirement], live: Sequence[Constraint]
) -> list[RetiredRequirement]:
    """The retired requirements a live one does not restate."""
    stated = {c.key for c in live}
    return [r for r in retired if r.constraint.key not in stated]


def unheld_withdrawals(
    withdrawals: Sequence[RequirementWithdrawal], *, held: Sequence[Constraint]
) -> list[str]:
    """The keys the withdrawals name that no held requirement carries."""
    keys = {c.key for c in held}
    return [w.key for w in withdrawals if w.key not in keys]


def restored(
    retired: Sequence[RetiredRequirement], *, turn_id: str, dropped: Sequence[str]
) -> tuple[list[Constraint], list[RetiredRequirement]]:
    """The requirements a declined message retired, and those it leaves retired.

    A message the researcher said no to takes back its withdrawals, and a
    requirement it replaced by one of the ``dropped`` keys is live again.
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
