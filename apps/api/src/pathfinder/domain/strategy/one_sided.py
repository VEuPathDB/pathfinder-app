from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

from pydantic import ValidationError
from veupathdb.domain.parameters import (
    NumberValue,
    ParamKind,
    ParamValue,
    param_value_from_raw,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.constraints import Constraint, RangeSide
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    RequirementLink,
)
from pathfinder.domain.strategy.value_binding import plain_value
from pathfinder.domain.strategy.value_text import NumberEnds

_RANGE: ParamKind = "number-range"
_OPPOSITE: dict[RangeSide, RangeSide] = {"lower": "upper", "upper": "lower"}
_END: dict[RangeSide, str] = {"lower": "low end", "upper": "high end"}
_LIMIT: dict[RangeSide, str] = {"lower": "minimum", "upper": "maximum"}


class _Sided(NamedTuple):
    param: str
    requirement: Constraint
    side: RangeSide

    @property
    def left_open(self) -> RangeSide:
        return _OPPOSITE[self.side]


def _sided(
    answers: Sequence[RequirementLink], requirements: Sequence[Constraint]
) -> list[_Sided]:
    held = {c.id: c for c in requirements}
    return [
        _Sided(link.param, stated, side)
        for link in answers
        if link.param is not None
        and (stated := held.get(link.requirement)) is not None
        and (side := stated.side) is not None
    ]


def _open_on_their_parameter(sided: Sequence[_Sided]) -> list[_Sided]:
    stated = {(s.param, s.side) for s in sided}
    return [s for s in sided if (s.param, s.left_open) not in stated]


def _open_on_the_step(sided: Sequence[_Sided]) -> list[_Sided]:
    stated = {s.side for s in sided}
    return [s for s in sided if s.left_open not in stated]


def _number(number: float) -> str:
    return NumberValue(value=number).to_wire()


def _default_end(info: ParameterInfo, end: RangeSide) -> float | None:
    if info.default_value is None:
        return None
    try:
        ends = NumberEnds.model_validate_json(info.default_value)
    except ValidationError:
        return None
    return ends.min if end == "lower" else ends.max


def _published(info: ParameterInfo, end: RangeSide) -> float | None:
    return info.min if end == "lower" else info.max


def _with_end(value: ParamValue, end: RangeSide, number: float) -> ParamValue | None:
    ends = NumberEnds.model_validate_json(value.to_wire())
    low, high = (number, ends.max) if end == "lower" else (ends.min, number)
    if low is not None and high is not None and low > high:
        return None
    return param_value_from_raw({"min": low, "max": high}, _RANGE)


def _correction(name: str, end: RangeSide, number: float, *, published: bool) -> str:
    if published:
        return (
            f"{name} binds its {_END[end]} at the site's published {_LIMIT[end]}, "
            f"{_number(number)}: the request states no {end} bound"
        )
    return (
        f"{name} keeps its {_END[end]} at the site's default, {_number(number)}: "
        f"the site publishes no {_LIMIT[end]} and the request states no {end} bound"
    )


def with_open_ends_bound(
    ranges: Mapping[str, ParamValue],
    answers: Sequence[RequirementLink],
    requirements: Sequence[Constraint],
    infos: Sequence[ParameterInfo],
) -> tuple[dict[str, ParamValue], list[str]]:
    by_name = {info.name: info for info in infos}
    bound = dict(ranges)
    corrections: list[str] = []
    for s in _open_on_their_parameter(_sided(answers, requirements)):
        if s.param not in bound:
            continue
        info, end = by_name[s.param], s.left_open
        limit = _published(info, end)
        number = limit if limit is not None else _default_end(info, end)
        if number is None:
            continue
        opened = _with_end(bound[s.param], end, number)
        if opened is None or opened == bound[s.param]:
            continue
        bound[s.param] = opened
        corrections.append(
            _correction(s.param, end, number, published=limit is not None)
        )
    return bound, corrections


def _scalar_number(bound: BoundValue) -> float | None:
    if not bound.number or bound.value.type not in ("number", "string"):
        return None
    try:
        return float(bound.value.to_wire())
    except ValueError:
        return None


def _a_number_at_the_site_default(bound: BoundValue) -> bool:
    if not bound.visible or bound.source != "default" or bound.placeholder:
        return False
    return bound.value.type == _RANGE or _scalar_number(bound) is not None


class _Held(NamedTuple):
    named: str
    number: float | None


def _held(criterion: Criterion, name: str, bound: BoundValue) -> _Held:
    shown = bound.rounded() or plain_value(bound.value)
    return _Held(f"{criterion.display_name_of(name)} {shown}", _scalar_number(bound))


def _crossed(low: _Held, high: _Held) -> list[str]:
    if low.number is None or high.number is None or low.number <= high.number:
        return []
    return [
        (
            f"{low.named} is above {high.named}. If these two bound one range, it "
            f"holds no value as bound, since the low end is above the high end"
        )
    ]


def _crossings(s: _Sided, linked: _Held, defaults: Sequence[_Held]) -> list[str]:
    return [
        sentence
        for held in defaults
        for sentence in (
            _crossed(held, linked) if s.side == "upper" else _crossed(linked, held)
        )
    ]


def _range_end_clause(bound: BoundValue, end: RangeSide) -> str:
    ends = NumberEnds.model_validate_json(bound.value.to_wire())
    held = ends.min if end == "lower" else ends.max
    limit = bound.published_min if end == "lower" else bound.published_max
    if held is None:
        return f"The range leaves its {_END[end]} open"
    if held == limit:
        return f"The {_END[end]} is the site's published {_LIMIT[end]}, {_number(held)}"
    return f"The {_END[end]} holds {_number(held)}, which the request does not state"


def _states(s: _Sided) -> str:
    return (
        f"The request states '{s.requirement.requested_value}' and no "
        f"{s.left_open} bound."
    )


def one_sided_notes(
    criterion: Criterion, requirements: Sequence[Constraint]
) -> dict[str, list[str]]:
    sided = _sided(criterion.answers, requirements)
    linked = {link.param for link in criterion.answers}
    values = criterion.resolved_params
    defaults = [
        _held(criterion, name, bound)
        for name, bound in values.items()
        if name not in linked and _a_number_at_the_site_default(bound)
    ]
    notes: dict[str, list[str]] = {}
    for s in _open_on_their_parameter(sided):
        if s.param in values and values[s.param].value.type == _RANGE:
            clause = _range_end_clause(values[s.param], s.left_open)
            notes.setdefault(s.param, []).append(f"{_states(s)} {clause}")
    if not defaults:
        return notes
    listed = ", ".join(held.named for held in defaults)
    held = f"Site defaults this step holds: {listed}"
    for s in _open_on_the_step(sided):
        if s.param in values and values[s.param].value.type != _RANGE:
            at = _held(criterion, s.param, values[s.param])
            told = ". ".join([held, *_crossings(s, at, defaults)])
            notes.setdefault(s.param, []).append(f"{_states(s)} {told}")
    return notes
