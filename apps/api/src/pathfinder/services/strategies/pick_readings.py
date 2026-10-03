"""The readings of a pick or a filter: the counts at the site's default and at
other options, and the options of the vocabulary a pick did not take."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

from veupathdb.domain.parameters import (
    FilterValue,
    MultiPickValue,
    ParamValue,
    from_wire,
    to_wire,
)
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.services.strategies.parameter_rules import rules_of
from pathfinder.services.strategies.value_labels import pick_terms

CountWith = Callable[[Mapping[str, ParamValue]], Awaitable[int | None]]
# A vocabulary this size is listed whole beside a pick; a larger one is named
# by the count of the options the pick did not take.
LISTED_OPTIONS = 30
# The other options of a single pick counted within the bind's budget.
COUNTED_OPTIONS = 3


def site_default(info: ParameterInfo) -> ParamValue | None:
    """The value the site sends when nothing is proposed; None for a pick whose
    default takes no option, which is no reading the search answers."""
    wire = info.default_value or ""
    if info.param_kind == "filter":
        return from_wire("filter", wire)
    default = from_wire(info.param_kind, wire) if wire.strip() else None
    return default if default is not None and pick_terms(default) else None


def _shown(value: ParamValue, info: ParameterInfo) -> str:
    """How a reader is shown another reading: its labels, or all of them."""
    options = info.vocabulary()
    terms = pick_terms(value)
    if options and len(terms) == len(options) > 1:
        return f"all {len(options):,} options"
    displays = {option.value: option.display for option in options}
    match value:
        case FilterValue(filters=[]):
            return "no filter"
        case _:
            return ", ".join(displays.get(t, t) for t in terms) or to_wire(value)


def tree_note(name: str, info: ParameterInfo) -> list[Measurement]:
    """Why a tree pick names no options not taken; nothing for a flat pick."""
    rules = rules_of(info)
    if not rules.reason or rules.measurement != "site_default":
        return []
    return [Measurement(kind="not_measurable", param=name, reading=rules.reason)]


def options_not_taken(
    name: str, value: ParamValue, info: ParameterInfo
) -> list[Measurement]:
    """The options of a flat vocabulary the pick did not take."""
    options = info.vocabulary()
    if info.allowed_values_tree is not None or not options:
        return []
    held = set(pick_terms(value))
    untaken = [o.display for o in options if o.value not in held]
    if not held or not untaken:
        return []
    return [
        Measurement(
            kind="options_not_taken",
            param=name,
            unchosen=untaken if len(options) <= LISTED_OPTIONS else [],
            unchosen_count=len(untaken),
        )
    ]


def _other_options(value: ParamValue, info: ParameterInfo) -> list[ParamValue]:
    """The options a single pick is counted at, the site default first."""
    default = site_default(info)
    others = [from_wire(info.param_kind, o.value) for o in info.vocabulary()]
    seen = {to_wire(value)}
    found: list[ParamValue] = []
    for other in [default, *others]:
        if other is None or to_wire(other) in seen:
            continue
        seen.add(to_wire(other))
        found.append(other)
    return found[:COUNTED_OPTIONS]


def _every_option(value: ParamValue, info: ParameterInfo) -> ParamValue | None:
    """Every option of a multi-pick that holds some of them, else None."""
    options = [o.value for o in info.vocabulary()]
    held = set(pick_terms(value))
    if not held or held >= set(options):
        return None
    return MultiPickValue(values=options)


async def _single_pick(
    count_with: CountWith, name: str, value: ParamValue, info: ParameterInfo, bound: int
) -> list[Measurement]:
    """A single pick is a choice when another option counts differently.

    The site default is recorded when the pick is another value and the site
    counted it; an option whose count did not arrive is no reading.
    """
    others = _other_options(value, info)
    counts = await asyncio.gather(*(count_with({name: o}) for o in others))
    default = site_default(info)
    found: list[Measurement] = []
    if (
        default is not None
        and others
        and to_wire(others[0]) == to_wire(default)
        and counts[0] is not None
    ):
        found.append(
            Measurement(
                kind="site_default",
                param=name,
                count=counts[0],
                reading=_shown(default, info),
            )
        )
    if any(c is not None and c != bound for c in counts):
        found.extend(options_not_taken(name, value, info))
    return [*found, *tree_note(name, info)]


async def _counted_once(
    count_with: CountWith, name: str, held: BoundValue, info: ParameterInfo, bound: int
) -> list[Measurement]:
    """A multi-pick or a filter at its site default when it holds another
    value, else a multi-pick at every option, its loosest bound. A reading
    whose count did not arrive is no reading."""
    value = held.value
    default = site_default(info)
    other: ParamValue | None = None
    kind: Literal["site_default", "loosest_bound"] = "site_default"
    if default is not None and not held.at_default:
        other = default
    elif info.param_kind == "multi-pick-vocabulary":
        other, kind = _every_option(value, info), "loosest_bound"
    if other is None:
        return tree_note(name, info)
    count = await count_with({name: other})
    if count is None:
        return tree_note(name, info)
    found = [
        Measurement(kind=kind, param=name, count=count, reading=_shown(other, info))
    ]
    if count != bound:
        found.extend(options_not_taken(name, value, info))
    return [*found, *tree_note(name, info)]


async def default_reading(
    count_with: CountWith, name: str, held: BoundValue, info: ParameterInfo, bound: int
) -> list[Measurement]:
    """The counts at the other readings of a pick or a filter, and the options
    a pick did not take when one of those counts differs from ``bound``.
    ``info`` is the published sheet entry, whose initial value is the site's
    default."""
    if info.param_kind == "single-pick-vocabulary":
        return await _single_pick(count_with, name, held.value, info, bound)
    return await _counted_once(count_with, name, held, info, bound)


__all__ = [
    "COUNTED_OPTIONS",
    "LISTED_OPTIONS",
    "CountWith",
    "default_reading",
    "site_default",
    "tree_note",
]
