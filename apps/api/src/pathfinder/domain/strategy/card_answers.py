"""What an answered question card writes into the spec."""

from __future__ import annotations

from collections import defaultdict

from veupathdb.domain.parameters import (
    ParamKind,
    ParamValue,
    from_wire,
    param_value_from_raw,
)

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SetValues
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
        held[c.id] |= set(c.resolved_params) | {s.param_name for s in c.open_params}
    for slot in spec.open_slots:
        held[slot.criterion_id].add(slot.param_name)
    return held


def _option_value(kind: ParamKind, value: str) -> ParamValue:
    """The option's value in the parameter's kind; a pick option names one term."""
    if kind in _OBJECT_KINDS:
        return from_wire(kind, value)
    return param_value_from_raw(value, kind)


def _kind_of(criterion: Criterion, name: str, slots: list[OpenSlot]) -> ParamKind:
    """The kind of the parameter: its bound value's, else the kind its slot holds."""
    held = criterion.resolved_params.get(name)
    if held is not None:
        return held.value.type
    kinds: dict[str, ParamKind] = {s.param_name: s.param_kind for s in slots}
    return kinds.get(name, _TEXT)


def _card_bound(
    criterion: Criterion, binding: SetValues, option_id: str, slots: list[OpenSlot]
) -> Criterion:
    slots = [*criterion.open_params, *slots]
    for name, value in binding.params.items():
        kind = _kind_of(criterion, name, slots)
        criterion = criterion_restated(
            criterion,
            name,
            _option_value(kind, value),
            source="card",
            basis=option_id,
        )
    return criterion


def spec_bound_by_card(
    spec: OperationalSpec, binding: SetValues, *, option_id: str
) -> OperationalSpec:
    """The spec with the option's values bound as the card's.

    A value takes the kind of the value it replaces or of the slot it fills. A
    binding on a criterion the spec no longer holds binds nothing.
    """
    if all(c.id != binding.criterion_id for c in spec.criteria):
        return spec
    slots = [s for s in spec.open_slots if s.criterion_id == binding.criterion_id]
    return spec.model_copy(
        update={
            "criteria": [
                _card_bound(c, binding, option_id, slots)
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
