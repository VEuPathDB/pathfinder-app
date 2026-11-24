"""What an answered question card writes into the spec."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence

from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    FilterValue,
    HeldValue,
    MultiPickValue,
    ParamKind,
    ParamValue,
    PhyleticExpression,
    from_wire,
    value_kind,
)
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ParameterInfo

from strategist.domain.strategy.expression_handles import (
    BuiltPattern,
    UnknownExpressionError,
    held_expressions,
    resolved_params,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from strategist.domain.strategy.question_options import SetValues
from strategist.domain.strategy.readings import AcceptedReading
from strategist.domain.strategy.spec_replay import criterion_restated

_TEXT: ParamKind = "string"


def params_held(
    spec: OperationalSpec, sets_the_site: Callable[[str, str], bool]
) -> dict[str, set[str]]:
    """The parameters each criterion holds, bound or open, by criterion id.
    A parameter the site sets is held by no criterion."""
    held: dict[str, set[str]] = defaultdict(set)
    for c in spec.criteria:
        names = set(c.resolved_params) | {s.param_name for s in c.open_params}
        held[c.id] |= {n for n in names if not sets_the_site(c.search_name, n)}
    for slot in spec.open_slots:
        held[slot.criterion_id].add(slot.param_name)
    return held


def _not_a_value(name: str, value: str | list[str], why: str) -> ValidationError:
    return ValidationError(title=f"{value!r} is not a value of {name}", detail=why)


def _option_value(name: str, kind: ParamKind, value: str | list[str]) -> ParamValue:
    """The option's value in the parameter's kind; a pick option names one term,
    or lists its terms."""
    picks = kind == "multi-pick-vocabulary"
    match value:
        case list() if picks:
            return MultiPickValue(values=value)
        case list():
            raise _not_a_value(name, value, f"it takes one {kind} value")
        case _ if picks:
            return MultiPickValue(values=[value])
        case _:
            try:
                return from_wire(kind, value)
            except (ValueError, TypeError) as unread:
                why = f"it takes a {kind} value"
                raise _not_a_value(name, value, why) from unread


def _card_value(
    name: str,
    kind: ParamKind,
    value: str | list[str],
    sheet: Sequence[ParameterInfo],
) -> ParamValue:
    match value:
        case str() if name == PHYLETIC_EXPRESSION_PARAM:
            try:
                PhyleticExpression.parse(value)
            except (ValidationError, ValueError) as refused:
                raise _not_a_value(name, value, str(refused)) from refused
        case _:
            pass
    match _option_value(name, kind, value):
        case FilterValue() as held:
            facets = next((i.facets() for i in sheet if i.name == name), None)
            return held if facets is None else facets.held(held)
        case read:
            return read


def _kind_of(
    criterion: Criterion,
    name: str,
    slots: list[OpenSlot],
    sheet: Sequence[ParameterInfo],
) -> ParamKind:
    """The kind of the parameter: its bound value's, else its slot's, else the
    kind its published sheet gives it."""
    held = criterion.resolved_params.get(name)
    kind = value_kind(held.value) if held is not None else None
    if kind is not None:
        return kind
    kinds: dict[str, ParamKind] = {i.name: i.param_kind for i in sheet}
    kinds |= {s.param_name: s.param_kind for s in slots}
    return kinds.get(name, _TEXT)


def _restates(held: ParamValue, value: str | list[str]) -> bool:
    match value:
        case str():
            return held == HeldValue(wire=value)
        case _:
            return False


def option_value(criterion: Criterion, name: str, value: str | list[str]) -> ParamValue:
    kind = _kind_of(criterion, name, list(criterion.open_params), [])
    return _option_value(name, kind, value)


def _card_bound(
    criterion: Criterion,
    binding: SetValues,
    option_id: str,
    slots: list[OpenSlot],
    sheet: Sequence[ParameterInfo],
) -> Criterion:
    slots = [*criterion.open_params, *slots]
    site_set = {i.name for i in sheet if i.site_set}
    for name, value in binding.params.items():
        if name in site_set:
            continue
        held = criterion.resolved_params.get(name)
        criterion = criterion_restated(
            criterion,
            name,
            held.value
            if held is not None and _restates(held.value, value)
            else _card_value(
                name, _kind_of(criterion, name, slots, sheet), value, sheet
            ),
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
    criterion's sheet in ``sheets``, keyed by criterion id. A value takes the kind
    of the value it replaces or the slot it fills; a gone criterion binds nothing."""
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
                _card_bound(c, binding, option_id, slots, sheets.get(c.id, []))
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


def option_refusal(
    spec: OperationalSpec,
    binding: SetValues,
    *,
    sheets: Mapping[str, Sequence[ParameterInfo]],
    expressions: Mapping[str, BuiltPattern],
) -> str | None:
    try:
        spec_bound_by_card(
            spec, binding, option_id="", sheets=sheets, expressions=expressions
        )
    except ValidationError as refused:
        return str(refused)
    return None
