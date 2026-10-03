"""Grounding a stated fold-change requirement against the fold-change cuts
the strategy holds."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import NamedTuple

from pathfinder.domain.constraint_check import agrees
from pathfinder.domain.log2_scale import Scale, scale_of, stated_numbers
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintStatus,
    GroundedConstraint,
)
from pathfinder.domain.strategy.realized_spec import RealizedSpec, awaiting_analysis

FOLD_PARAM = "fold_change"
_BARE_NUMBER = re.compile(r"\d+(?:\.\d+)?")
# A fold requirement with these words and no number states no cut.
_NO_CUT_RE = re.compile(r"\b(?:no|none|any|without)\b", re.IGNORECASE)


class _FoldReading(NamedTuple):
    """A fold-change threshold the strategy holds, on the scale it declares."""

    param: str
    value: float
    scale: Scale


def _requested_fold(c: Constraint) -> tuple[float, Scale] | None:
    """The one number the requirement states, on the scale it names; a bare
    number of a fold-change requirement is a fold."""
    stated = stated_numbers(c.requested_value)
    if len(stated) == 1:
        return stated[0].number, stated[0].scale
    bare = _BARE_NUMBER.findall(c.requested_value)
    if not stated and len(bare) == 1:
        return float(bare[0]), "fold"
    return None


def _fold_readings(realized: RealizedSpec) -> list[_FoldReading]:
    """Each analysis cut, on the scale its compute names and log2 when it names
    none, and each fold-change parameter, on the scale its display name names
    and fold when it names none."""
    shown = {
        name: k.display_name_of(name)
        for k in realized.criteria
        for name in k.resolved_params
    }
    readings = [
        _FoldReading(
            "effect_size_threshold",
            k.analysis.effect_size_threshold,
            scale_of(k.analysis.effect_size_label) or "log2",
        )
        for k in realized.criteria
        if k.analysis is not None and k.analysis.effect_size_threshold is not None
    ]
    for name, raw in realized.param_values.items():
        if FOLD_PARAM in name and _BARE_NUMBER.fullmatch(raw):
            display = shown.get(name, name)
            readings.append(_FoldReading(name, float(raw), scale_of(display) or "fold"))
    return readings


def _convert(source: Scale, target: Scale) -> Callable[[float], float]:
    if source == target:
        return float
    return math.log2 if target == "log2" else lambda value: 2**value


def _meets(requested: tuple[float, Scale], reading: _FoldReading) -> bool:
    number, scale = requested
    return agrees(
        number,
        reading.value,
        to_bound=_convert(scale, reading.scale),
        to_requested=_convert(reading.scale, scale),
    )


def _built(reading: _FoldReading) -> str:
    fold = _convert(reading.scale, "fold")(reading.value)
    on_log2 = f" (log2 {reading.value:g})" if reading.scale == "log2" else ""
    return f"{fold:g}-fold{on_log2}"


def _effect(analysis: AnalysisBinding) -> float | None:
    return analysis.effect_size_threshold


def _ground_no_fold_cut(
    c: Constraint, realized: RealizedSpec, readings: list[_FoldReading]
) -> GroundedConstraint:
    """A requirement for no fold cut: met by a cut at 1-fold or by a compute
    with no effect size cut."""
    flat = next((r for r in readings if _convert(r.scale, "fold")(r.value) <= 1), None)
    if flat is not None or realized.uncut(_effect):
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.GROUNDED,
            realized_value=None if flat is None else f"{flat.value:g}",
            realized_param="" if flat is None else flat.param,
        )
    if realized.analysis_pending:
        return awaiting_analysis(c)
    if not readings:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            note="no fold_change parameter in the strategy",
        )
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.SUBSTITUTED,
        realized_value=f"{readings[0].value:g}",
        realized_param=readings[0].param,
        note=f"built {_built(readings[0])} where {c.requested_value} was asked",
    )


def ground_fold_change(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    """The requirement against each fold-change threshold, compared in the
    threshold's own scale at the decimals each value is written with."""
    readings = _fold_readings(realized)
    requested = _requested_fold(c)
    if requested is None and _NO_CUT_RE.search(c.requested_value):
        return _ground_no_fold_cut(c, realized, readings)
    if not readings or requested is None:
        held = readings or any(FOLD_PARAM in name for name in realized.param_names)
        if not held and realized.awaits_analysis(_effect):
            return awaiting_analysis(c)
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.GROUNDED if held else ConstraintStatus.UNGROUNDABLE,
            note="" if held else "no fold_change parameter in the strategy",
        )
    reading = next((r for r in readings if _meets(requested, r)), None)
    if reading is not None:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.GROUNDED,
            realized_value=f"{reading.value:g}",
            realized_param=reading.param,
        )
    first = readings[0]
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.SUBSTITUTED,
        realized_value=f"{first.value:g}",
        realized_param=first.param,
        note=f"built {_built(first)} where {c.requested_value} was asked",
    )
