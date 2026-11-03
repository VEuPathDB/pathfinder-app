from __future__ import annotations

from collections.abc import Collection

from pathfinder.domain.site_checks import CheckStatus, SiteCheck, UncheckedReason
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
    GroundedConstraint,
    RecordTypeValue,
    is_blocking,
)

_UNMET = frozenset({ConstraintStatus.SUBSTITUTED, ConstraintStatus.UNGROUNDABLE})


def _judged(
    c: Constraint,
    status: CheckStatus,
    evidence: str,
    why: UncheckedReason = "no_check",
) -> SiteCheck:
    return SiteCheck(
        kind=c.kind,
        subject=c.requested_value,
        status=status,
        evidence=evidence,
        requirement=c.id,
        why_unchecked=why if status == "unchecked" else None,
    )


def grounded_check(grounded: GroundedConstraint) -> SiteCheck:
    c = grounded.constraint
    if grounded.unverified is not None:
        return _judged(c, "unchecked", grounded.note, grounded.unverified)
    if grounded.status in _UNMET:
        said = grounded.note or f"the strategy states {grounded.realized_value}"
        return _judged(c, "fail" if is_blocking(grounded) else "unchecked", said)
    if grounded.status is ConstraintStatus.GROUNDED and grounded.realized_value:
        param = f"{grounded.realized_param} = " if grounded.realized_param else ""
        stated = f"the strategy states {param}{grounded.realized_value}"
        return _judged(c, "pass", grounded.note or stated)
    return _judged(
        c, "unchecked", grounded.note or "no check reads this requirement on the site"
    )


def record_type_check(
    c: Constraint, root_class: str | None, step_classes: Collection[str]
) -> SiteCheck:
    match c.value:
        case RecordTypeValue() as asked:
            pass
        case _:
            return _judged(
                c, "unchecked", "no typed record class to compare", "untyped"
            )
    named = asked.answering_classes
    if asked.role == "through":
        through = sorted(set(step_classes) & named)
        if through:
            return _judged(c, "pass", f"a step of the strategy returns {through[0]}")
        return _judged(c, "fail", "no step of the strategy returns these records")
    if root_class is None:
        return _judged(c, "unchecked", "the site names no record class for the result")
    status: CheckStatus = "pass" if root_class in named else "fail"
    return _judged(c, status, f"the result step returns {root_class} records")


__all__ = ["grounded_check", "record_type_check"]
