"""Grounding a stated fold-change requirement against the fold-change cuts
and directions its linking criteria hold."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import NamedTuple

from pathfinder.domain.constraint_check import agrees
from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.domain.log2_scale import Scale, scale_of
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
    FoldChangeValue,
    FoldDirection,
    GroundedConstraint,
)
from pathfinder.domain.strategy.linked_values import (
    NO_LINK,
    linked_analyses,
    linked_params,
    unread,
    untyped,
)
from pathfinder.domain.strategy.realized_spec import RealizedSpec

FOLD_PARAM = "fold_change"
_DIRECTION: dict[FoldDirection, EdaEffectDirection] = {
    "up": "upOnly",
    "down": "downOnly",
}


class _FoldReading(NamedTuple):
    """A fold-change threshold a linking criterion holds, on the scale it declares."""

    param: str
    value: float
    scale: Scale


def _fold_readings(c: Constraint, realized: RealizedSpec) -> list[_FoldReading]:
    """Each linked analysis cut, on the scale its compute names and log2 when it
    names none, and each linked parameter, on the scale its display name names
    and fold when it names none."""
    analyses = [
        _FoldReading(
            "effect_size_threshold", cut, scale_of(a.effect_size_label) or "log2"
        )
        for a in linked_analyses(c, realized.criteria)
        if (cut := a.effect_size_threshold) is not None
    ]
    params = [
        _FoldReading(p.name, number, scale_of(p.display_name) or "fold")
        for p in linked_params(c, realized.criteria)
        if (number := p.number) is not None
    ]
    return [*analyses, *params]


def _convert(source: Scale, target: Scale) -> Callable[[float], float]:
    if source == target:
        return float
    return math.log2 if target == "log2" else lambda value: 2**value


def _meets(cut: float, scale: Scale, reading: _FoldReading) -> bool:
    return agrees(
        cut,
        reading.value,
        to_bound=_convert(scale, reading.scale),
        to_requested=_convert(reading.scale, scale),
    )


def _built(reading: _FoldReading) -> str:
    fold = _convert(reading.scale, "fold")(reading.value)
    on_log2 = f" (log2 {reading.value:g})" if reading.scale == "log2" else ""
    return f"{fold:g}-fold{on_log2}"


def _asked(cut: float, scale: Scale) -> str:
    return f"{cut:g}-fold" if scale == "fold" else f"log2 {cut:g}"


def _effect(analysis: AnalysisBinding) -> float | None:
    return analysis.effect_size_threshold


def _directions(c: Constraint, realized: RealizedSpec) -> list[EdaEffectDirection]:
    return [
        d
        for a in linked_analyses(c, realized.criteria)
        if (d := a.effect_direction) is not None
    ]


def _another_direction(
    c: Constraint, asked: FoldChangeValue, realized: RealizedSpec
) -> GroundedConstraint | None:
    wanted = _DIRECTION.get(asked.direction)
    off = next((d for d in _directions(c, realized) if d != wanted), None)
    if wanted is None or off is None:
        return None
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.SUBSTITUTED,
        realized_value=off,
        realized_param="effect_direction",
        note=f"built {off} where {asked.direction} was asked",
    )


def _direction_only(
    c: Constraint, asked: FoldChangeValue, realized: RealizedSpec
) -> GroundedConstraint:
    stated = _directions(c, realized)
    if asked.direction == "either" or not stated:
        return unread(c, realized, "no linked analysis states a direction")
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        realized_value=stated[0],
        realized_param="effect_direction",
    )


def _uncut(c: Constraint, realized: RealizedSpec) -> bool:
    return any(
        a.method is not None and a.effect_size_threshold is None
        for a in linked_analyses(c, realized.criteria)
    )


def ground_fold_change(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    """The requirement against each linked fold-change threshold, compared in
    the threshold's own scale at the decimals each value is written with."""
    match c.value:
        case FoldChangeValue() as asked:
            pass
        case _:
            return untyped(c)
    turned = _another_direction(c, asked, realized)
    if turned is not None:
        return turned
    if asked.cut is None:
        return _direction_only(c, asked, realized)
    cut, scale = asked.cut, asked.scale
    if _convert(scale, "fold")(cut) == 1 and _uncut(c, realized):
        return GroundedConstraint(constraint=c, status=ConstraintStatus.GROUNDED)
    readings = _fold_readings(c, realized)
    if not readings:
        return unread(c, realized, NO_LINK, cut=_effect)
    off = next((r for r in readings if not _meets(cut, scale, r)), None)
    shown = readings[0] if off is None else off
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED
        if off is None
        else ConstraintStatus.SUBSTITUTED,
        realized_value=f"{shown.value:g}",
        realized_param=shown.param,
        note=""
        if off is None
        else f"built {_built(off)} where {_asked(cut, scale)} was asked",
    )
