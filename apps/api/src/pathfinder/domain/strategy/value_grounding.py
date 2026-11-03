from __future__ import annotations

from typing import Literal, NamedTuple

from pathfinder.domain.constraint_check import agrees
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
    GroundedConstraint,
    PercentileValue,
    SignificanceValue,
)
from pathfinder.domain.strategy.linked_values import (
    NO_LINK,
    LinkedParam,
    linked_analyses,
    linked_params,
    not_verified,
    unread,
)
from pathfinder.domain.strategy.realized_spec import RealizedSpec

UNTYPED = "no typed value to compare"
_FULL_SCALE = 100.0

type _Held = Literal["min", "max"]


def _plain(number: float) -> str:
    return str(int(number)) if number.is_integer() else str(number)


def _held_end(name: str) -> _Held | None:
    lowered = name.casefold()
    if "min" in lowered:
        return "min"
    if "max" in lowered:
        return "max"
    return None


def _expected(asked: PercentileValue, held: _Held) -> float:
    if asked.end == "top":
        return _FULL_SCALE - asked.share if held == "min" else _FULL_SCALE
    return 0.0 if held == "min" else asked.share


def _binding_end(asked: PercentileValue) -> _Held:
    return "min" if asked.end == "top" else "max"


def _share_of(asked: PercentileValue, bound: float) -> float:
    return _FULL_SCALE - bound if asked.end == "top" else bound


def _off_note(asked: PercentileValue, held: _Held, bound: float) -> str:
    if held == _binding_end(asked):
        meant = _plain(_share_of(asked, bound))
        return f"bound {_plain(bound)} means {asked.end} {meant}%"
    return (
        f"bound {_plain(bound)} cuts the {asked.end} {_plain(asked.share)}% at its "
        f"other end"
    )


class _HeldBound(NamedTuple):
    param: LinkedParam
    held: _Held
    number: float


def _held_bounds(c: Constraint, realized: RealizedSpec) -> list[_HeldBound]:
    return [
        _HeldBound(param, held, number)
        for param in linked_params(c, realized.criteria)
        if (held := _held_end(param.name)) is not None
        and (number := param.number) is not None
    ]


def ground_percentile(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    match c.value:
        case PercentileValue() as asked:
            pass
        case _:
            return not_verified(c, UNTYPED)
    bounds = _held_bounds(c, realized)
    off = next(
        (b for b in bounds if not agrees(_expected(asked, b.held), b.number)), None
    )
    if off is not None:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.SUBSTITUTED,
            realized_value=off.param.wire,
            realized_param=off.param.name,
            note=_off_note(asked, off.held, off.number),
        )
    at = next((b.param for b in bounds if b.held == _binding_end(asked)), None)
    if at is None:
        linked = linked_params(c, realized.criteria)
        why = f"no linked parameter holds the {asked.end} end" if linked else NO_LINK
        return unread(c, realized, why)
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        realized_value=at.wire,
        realized_param=at.name,
    )


def _significance(analysis: AnalysisBinding) -> float | None:
    return analysis.significance_threshold


def _significances(c: Constraint, realized: RealizedSpec) -> list[tuple[str, float]]:
    params = [
        (p.name, number)
        for p in linked_params(c, realized.criteria)
        if (number := p.number) is not None
    ]
    analyses = [
        ("significance_threshold", cut)
        for a in linked_analyses(c, realized.criteria)
        if (cut := a.significance_threshold) is not None
    ]
    return [*params, *analyses]


def ground_significance(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    match c.value:
        case SignificanceValue() as asked:
            pass
        case _:
            return not_verified(c, UNTYPED)
    held = _significances(c, realized)
    if not held:
        return unread(c, realized, NO_LINK, cut=_significance)
    off = next(((n, v) for n, v in held if not agrees(asked.at_most, v)), None)
    name, value = held[0] if off is None else off
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED
        if off is None
        else ConstraintStatus.SUBSTITUTED,
        realized_value=f"{value:g}",
        realized_param=name,
        note="" if off is None else f"asked {asked.at_most:g}, built {value:g}",
    )
