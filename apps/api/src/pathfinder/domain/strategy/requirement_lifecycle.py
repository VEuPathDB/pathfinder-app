"""The requirements a thread no longer holds live, each with its lifecycle."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Annotated

from pydantic import ConfigDict, Discriminator, model_validator
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.combination_check import (
    combination_terms_overlap,
    match_terms,
)
from pathfinder.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    ReplacedLifecycle,
    WithdrawnLifecycle,
    states_the_content,
)
from pathfinder.domain.strategy.message_reading import message_states_constraint
from pathfinder.domain.strategy.operational_spec import Criterion

RetiredLifecycle = Annotated[
    WithdrawnLifecycle | ReplacedLifecycle, Discriminator("state")
]

# The kinds a thread holds any number of values of. Every other kind holds one
# value, so a new value of it replaces the old one.
MANY_VALUED_KINDS = frozenset({ConstraintKind.OTHER, ConstraintKind.COMBINATION})


class RetiredRequirement(CamelModel):
    """A requirement the thread no longer holds live, and why."""

    model_config = ConfigDict(frozen=True)

    constraint: Constraint
    lifecycle: RetiredLifecycle
    # The terms of a withdrawn combination whose criteria a delete removed.
    sides: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _only_a_withdrawn_combination_has_sides(self) -> RetiredRequirement:
        if self.sides and (
            self.constraint.kind is not ConstraintKind.COMBINATION
            or self.lifecycle.state != "withdrawn"
        ):
            msg = "only a withdrawn combination names the sides a delete removed"
            raise ValueError(msg)
        return self

    def shown_requirements(self) -> list[str]:
        """The requirement each row of this retirement names.

        A withdrawn combination names only the sides a delete removed. A step
        can still answer each other side.
        """
        if self.sides:
            return list(self.sides)
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


def _values_name_each_other(held: Constraint, stated: Constraint) -> bool:
    a, b = held.requested_value, stated.requested_value
    if held.kind is ConstraintKind.COMBINATION and combination_terms_overlap(a, b):
        return True
    return (
        message_states_constraint(a, stated)
        or message_states_constraint(b, held)
        or states_the_content(a, b)
        or states_the_content(b, a)
    )


def withdrawn_by(
    held: Sequence[Constraint], statements: Sequence[Constraint]
) -> list[Constraint]:
    """The held requirements that some statement of a message names.

    A statement names a held requirement of its kind when their values carry
    each other's words. A kind of one value held once is named by any value.
    """

    def _named(requirement: Constraint, stated: Constraint) -> bool:
        if stated.kind is not requirement.kind:
            return False
        alone = [c for c in held if c.kind is requirement.kind] == [requirement]
        return (
            alone and requirement.kind not in MANY_VALUED_KINDS
        ) or _values_name_each_other(requirement, stated)

    return [c for c in held if any(_named(c, s) for s in statements)]


def with_recorded_sources(
    statements: Sequence[Constraint], recorded: Sequence[Constraint]
) -> list[Constraint]:
    """Each withdrawn statement in the source of the first requirement it names.

    ``recorded`` is every requirement the thread holds or retired, live first.
    A statement that names no recorded requirement keeps its own source.
    """
    return [
        statement.model_copy(update={"source": named[0].source})
        for statement in statements
        for named in [withdrawn_by(recorded, [statement]) or [statement]]
    ]


def successor_of(
    requirement: Constraint, stated: Sequence[Constraint]
) -> Constraint | None:
    """The first requirement of the same kind the message states in its place."""
    return next(
        (c for c in stated if c.kind is requirement.kind and c.key != requirement.key),
        None,
    )


# Words with which a question asks for something in place of a requirement.
_ASKS_A_STAND_IN_RE = re.compile(
    r"\b(?:replace[sd]?|instead|stand[- ]?in|substitute[sd]?|proxy|alternative)\b",
    re.IGNORECASE,
)


def stood_in_for(
    held: Sequence[Constraint], *, prompt: str, stand_in: Constraint
) -> list[Constraint]:
    """The held requirements an answer to this question names a stand-in for.

    A question that asks for a replacement names, in its prompt, the
    requirement it replaces. An organism or a record type scopes the whole
    strategy, so no stand-in replaces either.
    """
    if not _ASKS_A_STAND_IN_RE.search(prompt):
        return []
    return [
        c
        for c in held
        if c.key != stand_in.key
        and c.kind not in STRATEGY_SCOPES
        and message_states_constraint(prompt, c)
    ]


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
    keys = {c.key for c in gone}

    def _lifecycle(requirement: Constraint) -> RetiredLifecycle:
        successor = stand_in or successor_of(requirement, stated)
        if successor is None:
            return WithdrawnLifecycle(turn_id=turn_id)
        return ReplacedLifecycle(by=successor.key)

    newly = [
        RetiredRequirement(constraint=c, lifecycle=_lifecycle(c))
        for c in held
        if c.key in keys
    ]
    retired_keys = {r.constraint.key for r in newly}
    return (
        [c for c in held if c.key not in retired_keys],
        [*(r for r in retired if r.constraint.key not in retired_keys), *newly],
    )


def dropped_sides(
    combination: Constraint,
    deleted: Sequence[Criterion],
    remaining: Sequence[Criterion],
) -> tuple[str, ...]:
    """The terms of a combination that name a deleted criterion.

    Each term names the criterion whose own text shares the most words with
    it. When the terms name no criteria one to one, no term is dropped.
    """
    request = CombinationRequest.parse(combination.requested_value)
    if request is None:
        return ()
    matched = match_terms(request.terms, [*deleted, *remaining])
    if matched is None:
        return ()
    named = {**matched.members, **matched.transforms, **matched.excludes}
    gone = {c.id for c in deleted}
    return tuple(term for term in request.terms if named[term] in gone)


def retire_dropped_sides(
    held: Sequence[Constraint],
    retired: Sequence[RetiredRequirement],
    *,
    deleted: Sequence[Criterion],
    remaining: Sequence[Criterion],
    turn_id: str,
) -> tuple[list[Constraint], list[RetiredRequirement]]:
    """The live and the retired requirements once a delete removes a side of a
    combination: the combination is withdrawn, and names the sides it lost."""
    withdrawn = [r.constraint for r in retired if r.lifecycle.state == "withdrawn"]
    sides = {
        c.key: dropped
        for c in [*held, *withdrawn]
        if c.kind is ConstraintKind.COMBINATION
        and (dropped := dropped_sides(c, deleted, remaining))
    }
    live, kept = retire(
        held, retired, [c for c in held if c.key in sides], turn_id=turn_id
    )
    return live, [
        RetiredRequirement(
            constraint=r.constraint,
            lifecycle=r.lifecycle,
            sides=sides[r.constraint.key],
        )
        if r.constraint.key in sides
        else r
        for r in kept
    ]


def reopened(
    retired: Sequence[RetiredRequirement], live: Sequence[Constraint]
) -> list[RetiredRequirement]:
    """The retired requirements a live one does not restate."""
    stated = {c.key for c in live}
    return [r for r in retired if r.constraint.key not in stated]


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
