"""What an answered question card writes into the spec."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from veupathdb.domain.parameters import (
    ParamKind,
    ParamValue,
    from_wire,
    param_value_from_raw,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    UnknownExpressionError,
    held_expressions,
    resolved_params,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.question_options import SetValues
from pathfinder.domain.strategy.readings import AcceptedReading
from pathfinder.domain.strategy.spec_replay import criterion_restated

_TEXT: ParamKind = "string"
# The kinds whose option value is the JSON object the site takes whole.
_OBJECT_KINDS: frozenset[ParamKind] = frozenset(
    {"number-range", "date-range", "filter"}
)


def params_held(spec: OperationalSpec) -> dict[str, set[str]]:
    """The parameters each criterion holds, bound or open, by criterion id."""
    held: dict[str, set[str]] = defaultdict(set)
    for c in spec.criteria:
        held[c.id] |= set(c.shown_values) | {s.param_name for s in c.open_params}
    for slot in spec.open_slots:
        held[slot.criterion_id].add(slot.param_name)
    return held


def _option_value(kind: ParamKind, value: str) -> ParamValue:
    """The option's value in the parameter's kind; a pick option names one term."""
    if kind in _OBJECT_KINDS:
        return from_wire(kind, value)
    return param_value_from_raw(value, kind)


def _kind_of(
    criterion: Criterion,
    name: str,
    slots: list[OpenSlot],
    sheet: Sequence[ParameterInfo],
) -> ParamKind:
    """The kind of the parameter: its bound value's, else its slot's, else the
    kind its published sheet gives it."""
    held = criterion.resolved_params.get(name)
    if held is not None:
        return held.value.type
    kinds: dict[str, ParamKind] = {i.name: i.param_kind for i in sheet}
    kinds |= {s.param_name: s.param_kind for s in slots}
    return kinds.get(name, _TEXT)


def option_value(criterion: Criterion, name: str, value: str) -> ParamValue:
    kind = _kind_of(criterion, name, list(criterion.open_params), [])
    return _option_value(kind, value)


def _card_bound(
    criterion: Criterion,
    binding: SetValues,
    option_id: str,
    slots: list[OpenSlot],
    sheet: Sequence[ParameterInfo],
) -> Criterion:
    slots = [*criterion.open_params, *slots]
    hidden = {i.name for i in sheet if not i.is_visible} | {
        name for name, held in criterion.resolved_params.items() if not held.visible
    }
    for name, value in binding.params.items():
        if name in hidden:
            continue
        kind = _kind_of(criterion, name, slots, sheet)
        criterion = criterion_restated(
            criterion,
            name,
            _option_value(kind, value),
            sheet=sheet,
            source="card",
            basis=option_id,
        )
    return criterion


def spec_with_reading(
    spec: OperationalSpec, criterion_id: str, accepted: AcceptedReading
) -> OperationalSpec:
    return spec.model_copy(
        update={
            "criteria": [
                c.model_copy(update={"accepted_reading": accepted})
                if c.id == criterion_id
                else c
                for c in spec.criteria
            ]
        }
    )


def spec_bound_by_card(
    spec: OperationalSpec,
    binding: SetValues,
    *,
    option_id: str,
    sheets: Mapping[str, Sequence[ParameterInfo]],
    expressions: Mapping[str, BuiltPattern],
) -> OperationalSpec:
    """The spec with the option's values bound as the card's, each read on the
    published sheet of its search in ``sheets``. A value takes the kind of the
    value it replaces or the slot it fills; a gone criterion binds nothing."""
    if all(c.id != binding.criterion_id for c in spec.criteria):
        return spec
    try:
        params = resolved_params(binding.params, held_expressions(expressions, spec))
    except UnknownExpressionError:
        return spec
    binding = binding.model_copy(update={"params": params})
    slots = [s for s in spec.open_slots if s.criterion_id == binding.criterion_id]
    return spec.model_copy(
        update={
            "criteria": [
                _card_bound(c, binding, option_id, slots, sheets.get(c.search_name, []))
                if c.id == binding.criterion_id
                else c
                for c in spec.criteria
            ],
            "open_slots": [
                s
                for s in spec.open_slots
                if s.criterion_id != binding.criterion_id
                or s.param_name not in binding.params
            ],
        }
    )
