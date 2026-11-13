from __future__ import annotations

import re
from typing import Literal, NamedTuple

from strategist.domain.constraint_check import agrees
from strategist.domain.strategy.analysis_binding import AnalysisBinding
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
    GroundedConstraint,
    PercentileValue,
    SignificanceValue,
    Statistic,
)
from strategist.domain.strategy.linked_values import (
    NO_LINK,
    LinkedParam,
    linked_analyses,
    linked_params,
    unread,
    untyped,
)
from strategist.domain.strategy.realized_spec import RealizedSpec

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
            return untyped(c)
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


class _HeldCut(NamedTuple):
    name: str
    value: float
    statistic: Statistic | None


_STATISTICS: tuple[tuple[re.Pattern[str], Statistic], ...] = (
    (re.compile(r"fdr|false discovery", re.IGNORECASE), "fdr"),
    (re.compile(r"q[\s_-]?val", re.IGNORECASE), "q_value"),
    (re.compile(r"adj", re.IGNORECASE), "adjusted_p"),
    (re.compile(r"p[\s_-]?val", re.IGNORECASE), "p_value"),
)


def _statistic_of(param: LinkedParam) -> Statistic | None:
    named = f"{param.name} {param.display_name}"
    return next((stat for found, stat in _STATISTICS if found.search(named)), None)


def _significances(c: Constraint, realized: RealizedSpec) -> list[_HeldCut]:
    params = [
        _HeldCut(p.name, number, _statistic_of(p))
        for p in linked_params(c, realized.criteria)
        if (number := p.number) is not None
    ]
    analyses = [
        _HeldCut("significance_threshold", cut, None)
        for a in linked_analyses(c, realized.criteria)
        if (cut := a.significance_threshold) is not None
    ]
    return [*params, *analyses]


def _another_statistic(asked: SignificanceValue, held: _HeldCut) -> bool:
    return (
        asked.statistic != "unspecified"
        and held.statistic is not None
        and held.statistic != asked.statistic
    )


def _off_cut(asked: SignificanceValue, held: _HeldCut) -> str:
    if _another_statistic(asked, held):
        return (
            f"asked {asked.statistic} <= {asked.at_most:g}, {held.name} holds a "
            f"{held.statistic} cut of {held.value:g}"
        )
    return f"asked {asked.at_most:g}, built {held.value:g}"


def ground_significance(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    match c.value:
        case SignificanceValue() as asked:
            pass
        case _:
            return untyped(c)
    held = _significances(c, realized)
    if not held:
        return unread(c, realized, NO_LINK, cut=_significance)
    off = next(
        (
            h
            for h in held
            if _another_statistic(asked, h) or not agrees(asked.at_most, h.value)
        ),
        None,
    )
    shown = held[0] if off is None else off
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED
        if off is None
        else ConstraintStatus.SUBSTITUTED,
        realized_value=f"{shown.value:g}",
        realized_param=shown.name,
        note="" if off is None else _off_cut(asked, off),
    )
