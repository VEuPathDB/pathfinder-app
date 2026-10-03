"""Binding parameter values with their source, as the published sheet reads them."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    from_wire,
    to_wire,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.number_precision import shown_decimals
from pathfinder.domain.strategy.operational_spec import BoundValue, ValueSource
from pathfinder.domain.strategy.value_label import value_label


def _at_default(value: ParamValue, published: str | None) -> bool:
    """Whether the value is the published initial value, read in its own kind."""
    if published is None:
        return False
    try:
        initial = from_wire(value.type, published)
    except ValueError:
        return False
    return to_wire(initial) == to_wire(value)


# The kinds of parameter a long decimal can bind: a number, or a pick of terms.
_NUMBER_KINDS = frozenset({"number", "single-pick-vocabulary"})


def researcher_sees(info: ParameterInfo) -> bool:
    """Whether the researcher sees the parameter: the sheet shows it, or its
    vocabulary offers a choice of more than one entry."""
    return info.is_visible or len(info.vocabulary()) > 1


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
        visible=researcher_sees(info),
        number=info.is_number or info.param_kind in _NUMBER_KINDS,
        decimals=shown_decimals(info.default_value),
    )


def bind_values(
    values: Mapping[str, ParamValue],
    source: ValueSource,
    sheet: Sequence[ParameterInfo],
    basis: str = "",
) -> dict[str, BoundValue]:
    """Each value bound with one source and basis, and read on the published
    sheet. A sheet read under bound values answers each sent value as its
    initial value, so it is never the sheet passed here."""
    by_name = {info.name: info for info in sheet}
    return {
        name: _bound(value, source, basis, by_name.get(name), sheet)
        for name, value in values.items()
    }


def read_again(
    values: Mapping[str, BoundValue], sheet: Sequence[ParameterInfo]
) -> dict[str, BoundValue]:
    """The values read on the sheet, each keeping who set it and why."""
    return {
        name: bind_values({name: held.value}, held.source, sheet, held.basis)[
            name
        ].model_copy(
            update={"carried_from": held.carried_from, "stated_as": held.stated_as}
        )
        for name, held in values.items()
    }


def plain_value(value: ParamValue) -> str:
    """A vocabulary term in readable form instead of its JSON wire form."""
    match value:
        case MultiPickValue(values=terms):
            return ", ".join(terms)
        case SinglePickValue(value=term):
            return term
        case _:
            return to_wire(value)
