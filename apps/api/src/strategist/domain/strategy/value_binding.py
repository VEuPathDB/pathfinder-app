"""Binding parameter values with their source, as the published sheet reads them."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence

from veupathdb.domain.parameters import (
    DateBounds,
    FilterValue,
    HeldValue,
    MultiPickValue,
    NumberBounds,
    ParamValue,
    SinglePickValue,
    from_wire_as,
    to_wire,
)
from veupathdb_mcp.catalog import ParameterInfo

from strategist.domain.strategy.number_precision import shown_decimals
from strategist.domain.strategy.operational_spec import BoundValue, ValueSource
from strategist.domain.strategy.value_label import value_label
from strategist.domain.strategy.value_text import (
    bounds_text,
    clause_text,
    filter_text,
)


def _at_default(value: ParamValue, published: str | None) -> bool:
    """Whether the value is the published initial value, read in its own kind."""
    if published is None:
        return False
    try:
        initial = from_wire_as(value, published)
    except ValueError:
        return False
    return to_wire(initial) == to_wire(value)


# The kinds of parameter a long decimal can bind: a number, or a pick of terms.
_NUMBER_KINDS = frozenset({"number", "single-pick-vocabulary"})


def _filter_words(value: ParamValue, info: ParameterInfo) -> str:
    match value:
        case FilterValue(filters=clauses):
            shown = {c.field: c.field for c in clauses} | {
                field.term: field.display for field in info.facets().root
            }
            return filter_text([clause_text(c, shown[c.field]) for c in clauses])
        case _:
            return ""


def _bound(
    value: ParamValue,
    source: ValueSource,
    basis: str,
    info: ParameterInfo | None,
    sheet: Sequence[ParameterInfo],
) -> BoundValue:
    if info is None:
        return BoundValue(value=value, source=source, basis=basis)
    return BoundValue(
        value=value,
        source=source,
        basis=basis,
        display_name=info.display_name,
        label=value_label(value, info, sheet),
        placeholder=info.is_placeholder(to_wire(value)),
        at_default=_at_default(value, info.default_value),
        visible=info.is_visible,
        number=info.is_number or info.param_kind in _NUMBER_KINDS,
        decimals=shown_decimals(info.default_value),
        words=_filter_words(value, info),
        published_min=info.min,
        published_max=info.max,
    )


def bind_values(
    values: Mapping[str, ParamValue],
    source: ValueSource,
    sheet: Sequence[ParameterInfo],
    basis: str = "",
) -> dict[str, BoundValue]:
    """Each value bound with one source and basis, and read on a sheet that holds
    the published defaults; its dependent vocabularies may be read under the
    bound parents."""
    by_name = {info.name: info for info in sheet}
    return {
        name: _bound(value, source, basis, by_name.get(name), sheet)
        for name, value in values.items()
    }


def read_again(
    values: Mapping[str, BoundValue], sheet: Sequence[ParameterInfo]
) -> dict[str, BoundValue]:
    """The values read on the sheet, each keeping who set it and why, and the
    label of the vocabulary it was bound under, which the sheet may lack."""
    return {
        name: _kept(
            held, bind_values({name: held.value}, held.source, sheet, held.basis)[name]
        )
        for name, held in values.items()
    }


def _kept(held: BoundValue, read: BoundValue) -> BoundValue:
    return read.model_copy(
        update={
            "carried_from": held.carried_from,
            "taxon": held.taxon,
            "label": held.label or read.label,
        }
    )


def parents_moved(
    values: Mapping[str, ParamValue],
    names: Collection[str],
    sheet: Sequence[ParameterInfo],
) -> bool:
    """Whether a parameter with one of these names has a dependent vocabulary,
    and one of its parents holds a value other than the published initial value.
    The published sheet is read under those initial values."""
    by_name = {info.name: info for info in sheet}
    parents = {
        parent
        for name in names
        if name in by_name
        for parent in by_name[name].wire_parents
    }
    return any(
        parent in values
        and parent in by_name
        and not _at_default(values[parent], by_name[parent].default_value)
        for parent in parents
    )


def pick_terms(value: ParamValue) -> list[str]:
    """The vocabulary terms a pick holds; none for any other value."""
    match value:
        case MultiPickValue(values=values):
            return list(values)
        case SinglePickValue(value=term):
            return [term]
        case _:
            return []


def agent_wire(value: ParamValue) -> str:
    match value:
        case HeldValue(wire=wire):
            return f"{wire!r} (kept as the site holds it)"
        case _:
            return to_wire(value)


def plain_value(value: ParamValue) -> str:
    """A vocabulary term in readable form instead of its JSON wire form."""
    match value:
        case MultiPickValue(values=terms):
            return ", ".join(terms)
        case SinglePickValue(value=term):
            return term
        case FilterValue(filters=clauses):
            return filter_text([clause_text(c) for c in clauses])
        case _ if value.type == "number-range":
            return bounds_text(NumberBounds.model_validate_json(to_wire(value)))
        case _ if value.type == "date-range":
            return bounds_text(DateBounds.model_validate_json(to_wire(value)))
        case _:
            return agent_wire(value)
