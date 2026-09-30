"""Grounding a stated constraint against the strategy that realizes it."""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import NamedTuple

from pydantic import Field
from veupathdb.domain.parameters import to_wire
from veupathdb.model import CamelModel

from pathfinder.domain.constraint_check import agrees
from pathfinder.domain.log2_scale import Scale, scale_of, stated_numbers
from pathfinder.domain.strategy.combination_check import (
    TermMatch,
    combination_violation,
    enough_members,
    exclusion_stands_over,
    match_terms,
    meeting_operator,
    transform_stands_over,
)
from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
    ConstraintStatus,
    GroundedConstraint,
    PercentileRequest,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)

_SIGNIFICANCE_RE = re.compile(
    r"p_?value|p_?adj|fdr|q_?value|significance", re.IGNORECASE
)
_MICROARRAY_RE = re.compile(r"microarray", re.IGNORECASE)
_RNASEQ_REQUEST_RE = re.compile(r"rna[\s_-]?seq", re.IGNORECASE)
_EXPRESSION_DATA_RE = re.compile(r"rnaseq|microarray", re.IGNORECASE)


class RealizedSpec(CamelModel):
    """The bound facts a constraint is grounded against: the criteria's WDK
    search names, the union of their parameter names, the values bound to them,
    the tree the criteria are combined in, and the type of the upload each
    criterion runs on, by criterion id."""

    search_names: list[str] = Field(default_factory=list)
    param_names: frozenset[str] = Field(default_factory=frozenset)
    param_values: dict[str, str] = Field(default_factory=dict)
    structure: SpecStructure | None = None
    criteria: list[Criterion] = Field(default_factory=list)
    upload_types: dict[str, str] = Field(default_factory=dict)


def _data_run_on(realized: RealizedSpec) -> list[str]:
    """The data each step runs on: the type of the upload it reads, else the
    curated search it runs."""
    on_uploads = {
        k.search_name for k in realized.criteria if k.id in realized.upload_types
    }
    return [
        *realized.upload_types.values(),
        *(s for s in realized.search_names if s not in on_uploads),
    ]


def _ground_data_type(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    expr = [d for d in _data_run_on(realized) if _EXPRESSION_DATA_RE.search(d)]
    if not expr:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            note="no step runs on expression data",
        )
    wants_rnaseq = bool(_RNASEQ_REQUEST_RE.search(c.requested_value))
    all_microarray = all(_MICROARRAY_RE.search(s) for s in expr)
    if wants_rnaseq and all_microarray:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.SUBSTITUTED,
            realized_value="microarray",
            note="requested RNA-Seq but only microarray searches were selected",
        )
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        realized_value="rna-seq" if wants_rnaseq else "microarray",
    )


def _ground_threshold(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    if any(_SIGNIFICANCE_RE.search(name) for name in realized.param_names) or any(
        k.analysis is not None and k.analysis.significance_threshold is not None
        for k in realized.criteria
    ):
        return GroundedConstraint(constraint=c, status=ConstraintStatus.GROUNDED)
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.UNGROUNDABLE,
        note="no selected search exposes a significance parameter",
    )


_FOLD_PARAM = "fold_change"
_BARE_NUMBER = re.compile(r"\d+(?:\.\d+)?")


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
        if _FOLD_PARAM in name and _BARE_NUMBER.fullmatch(raw):
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


def _ground_fold_change(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    """The requirement against each fold-change threshold, compared in the
    threshold's own scale at the decimals each value is written with."""
    readings = _fold_readings(realized)
    requested = _requested_fold(c)
    if not readings or requested is None:
        held = readings or any(_FOLD_PARAM in name for name in realized.param_names)
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


_PERCENTILE_PARAM_RE = re.compile(r"percentile", re.IGNORECASE)
# A "top" share is a lower bound on the percentile; a "bottom" share is an
# upper bound. The name of the WDK parameter says which end it holds.
_BOUND_WORD: dict[str, str] = {"top": "min", "bottom": "max"}


def dimension_of_parameter(name: str, display_name: str) -> ConstraintKind:
    """The dimension a value of this parameter states, read from its names."""
    if _PERCENTILE_PARAM_RE.search(name) or _PERCENTILE_PARAM_RE.search(display_name):
        return ConstraintKind.PERCENTILE
    if _SIGNIFICANCE_RE.search(name):
        return ConstraintKind.STATISTICAL_THRESHOLD
    if _FOLD_PARAM in name or scale_of(display_name) is not None:
        return ConstraintKind.FOLD_CHANGE
    return ConstraintKind.OTHER


def _plain(number: float) -> str:
    return str(int(number)) if number.is_integer() else str(number)


def _percentile_bound(
    request: PercentileRequest, realized: RealizedSpec
) -> tuple[str, str] | None:
    named = {
        name: value
        for name, value in realized.param_values.items()
        if _PERCENTILE_PARAM_RE.search(name)
    }
    if not named:
        return None
    word = _BOUND_WORD[request.direction]
    at_end = {name: value for name, value in named.items() if word in name.lower()}
    chosen = at_end or named
    if len(chosen) != 1:
        return None
    return next(iter(chosen.items()))


def _ground_percentile(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    request = PercentileRequest.parse(f"{c.requested_value} {c.label}")
    if request is None:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            note="the requested share and direction could not be read",
        )
    found = _percentile_bound(request, realized)
    if found is None:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            note="no percentile parameter in the strategy",
        )
    name, raw = found
    try:
        bound = float(raw)
    except ValueError:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.UNGROUNDABLE,
            realized_value=raw,
            realized_param=name,
            note=f"{name} holds {raw!r}, which is not a percentile",
        )
    if bound == request.bound:
        return GroundedConstraint(
            constraint=c,
            status=ConstraintStatus.GROUNDED,
            realized_value=raw,
            realized_param=name,
        )
    meant = _plain(request.share_of(bound))
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.SUBSTITUTED,
        realized_value=raw,
        realized_param=name,
        note=f"bound {_plain(bound)} means {request.direction} {meant}%",
    )


def _abstained(c: Constraint, why: str) -> GroundedConstraint:
    """A combination this strategy gives no answer about.

    An abstention never blocks: the words the user chose name no criterion of
    the spec, so nothing here contradicts them.
    """
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        note=f"the combination check abstained: {why}",
    )


def _why_it_says_nothing(matched: TermMatch, structure: SpecStructure) -> str | None:
    """Why this tree answers nothing about the stated combination, or None.

    A combine is read over two members or none. A transform the tree holds
    away from those members, and an exclusion it subtracts from no branch,
    describe another tree than this one.
    """
    if not enough_members(matched):
        return "fewer than two of its terms name criteria a combine joins"
    members = matched.members.values()
    if any(
        not transform_stands_over(structure, transform_id, members)
        for transform_id in matched.transforms.values()
    ):
        return "a transform it names stands over none of those criteria"
    if any(
        not exclusion_stands_over(structure, exclude_id, members)
        for exclude_id in matched.excludes.values()
    ):
        return "a criterion it removes is subtracted from no branch"
    return None


def _ground_combination(c: Constraint, realized: RealizedSpec) -> GroundedConstraint:
    request = CombinationRequest.parse(c.requested_value)
    if request is None:
        return _abstained(c, "the requirement states no single operator")
    matched = match_terms(request.terms, realized.criteria)
    if matched is None:
        return _abstained(c, "its terms name no distinct criteria of this strategy")
    if realized.structure is None:
        return _abstained(c, "the strategy has no structure yet")
    silent = _why_it_says_nothing(matched, realized.structure)
    if silent is not None:
        return _abstained(c, silent)
    members = matched.members.values()
    violation = combination_violation(request, members, realized.structure)
    if violation is not None:
        return GroundedConstraint(
            constraint=c, status=ConstraintStatus.UNGROUNDABLE, note=violation
        )
    found = meeting_operator(realized.structure, members)
    return GroundedConstraint(
        constraint=c,
        status=ConstraintStatus.GROUNDED,
        realized_value=None if found is None else found.value,
    )


_NO_UPLOADS: Mapping[str, str] = MappingProxyType({})

_HANDLERS = {
    ConstraintKind.DATA_TYPE: _ground_data_type,
    ConstraintKind.STATISTICAL_THRESHOLD: _ground_threshold,
    ConstraintKind.FOLD_CHANGE: _ground_fold_change,
    ConstraintKind.PERCENTILE: _ground_percentile,
    ConstraintKind.COMBINATION: _ground_combination,
}


def ground_constraints(
    constraints: list[Constraint], realized: RealizedSpec
) -> list[GroundedConstraint]:
    """Ground each constraint against the realized strategy facts."""
    out: list[GroundedConstraint] = []
    for c in constraints:
        handler = _HANDLERS.get(c.kind)
        if handler is None:
            out.append(
                GroundedConstraint(constraint=c, status=ConstraintStatus.GROUNDED)
            )
        else:
            out.append(handler(c, realized))
    return out


def _param_names(spec: OperationalSpec) -> set[str]:
    names = {p for c in spec.criteria for p in c.resolved_params}
    names |= {s.param_name for c in spec.criteria for s in c.open_params}
    return names | {s.param_name for s in spec.open_slots}


def ground_against_spec(
    constraints: Sequence[Constraint],
    spec: OperationalSpec,
    *,
    upload_types: Mapping[str, str] = _NO_UPLOADS,
) -> list[GroundedConstraint]:
    """Ground each constraint against the facts this spec realizes and the type
    of the upload each criterion runs on."""
    return ground_constraints(
        list(constraints),
        RealizedSpec(
            search_names=[c.search_name for c in spec.criteria if c.search_name],
            param_names=frozenset(_param_names(spec)),
            param_values={
                name: to_wire(value)
                for c in spec.criteria
                for name, value in c.param_values.items()
            },
            structure=spec.structure,
            criteria=spec.criteria,
            upload_types=dict(upload_types),
        ),
    )
