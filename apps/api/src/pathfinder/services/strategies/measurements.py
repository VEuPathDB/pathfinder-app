"""The counts the site returns for other readings of a bound value, by the
rule its parameter class names. A turn reads one configuration once."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from veupathdb import get_logger
from veupathdb.domain.parameters import (
    NumberValue,
    ParamValue,
    PhyleticBinding,
    PhyleticTree,
    StringValue,
    derive_binding,
    param_value_from_raw,
    to_wire,
)
from veupathdb.errors import VEuPathDBError, WDKError
from veupathdb.wdk import SiteSearchResponse, get_site_router
from veupathdb_mcp.catalog import ParameterInfo
from veupathdb_mcp.wdk import count_search_answer

from pathfinder.domain.strategy.operational_spec import BoundValue, Measurement
from pathfinder.domain.strategy.text_expression import TextExpression
from pathfinder.services.strategies.parameter_rules import rules_of, text_query
from pathfinder.services.strategies.pick_readings import default_reading, tree_note
from pathfinder.services.strategies.value_labels import pick_terms

logger = get_logger(__name__)

CountKey = tuple[str, str, str, str]
ReachKey = tuple[str, str, tuple[str, ...]]

# The WDK parameters that list the species a phylogenetic profile requires
# and the ones it forbids.
_INCLUDED_SPECIES = "included_species"
_EXCLUDED_SPECIES = "excluded_species"
_MEASURED_SOURCES = frozenset({"default", "chosen"})
# A group is two species or more; one species reads the same both ways.
_SMALLEST_GROUP = 2
# A number the site publishes no bound for is read at zero.
_UNBOUNDED_READING = 0.0
# The reads of one bind share this budget, apart from the bind's own count:
# they run beside each other, and a reading that has not arrived by then is
# recorded as not measured.
MEASUREMENT_BUDGET_SECONDS = 20.0


@dataclass
class TurnCounts:
    """The counts and the site-search answers one turn read.

    A count that did not arrive is not held, so a later reading asks again.
    """

    counts: dict[CountKey, int] = field(default_factory=dict)
    reaches: dict[ReachKey, SiteSearchResponse] = field(default_factory=dict)

    async def count(
        self,
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
        *,
        timeout_seconds: float,
    ) -> int | None:
        """The records one configuration of the search answers, None when the
        service did not answer it."""
        config = json.dumps(
            {name: to_wire(value) for name, value in params.items()}, sort_keys=True
        )
        key = (site_id, record_type, search_name, config)
        if key not in self.counts:
            try:
                counted = await count_search_answer(
                    site_id,
                    record_type,
                    search_name,
                    params,
                    timeout_seconds=timeout_seconds,
                )
            except WDKError as exc:
                logger.warning("Count did not answer", site_id=site_id, error=str(exc))
                return None
            if counted is None:
                return None
            self.counts[key] = counted
        return self.counts[key]

    async def reach(
        self,
        site_id: str,
        phrase: str,
        organisms: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> SiteSearchResponse | None:
        """The site search's answer for the phrase, None when it did not answer."""
        key = (site_id, phrase, tuple(organisms))
        if key not in self.reaches:
            try:
                async with asyncio.timeout(timeout_seconds):
                    answer = await (
                        get_site_router()
                        .get_site_search_client(site_id)
                        .search(phrase, organisms=list(organisms) or None, limit=0)
                    )
            except (VEuPathDBError, TimeoutError) as exc:
                logger.warning(
                    "Site search did not answer", site_id=site_id, error=str(exc)
                )
                return None
            self.reaches[key] = answer
        return self.reaches[key]


@dataclass(frozen=True)
class MeasuredBinding:
    """A bound search as its count ran: the values it sent and what it counted."""

    site_id: str
    record_type: str
    search_name: str
    params: Mapping[str, ParamValue]
    count: int | None
    organism_param: str | None = None

    def organisms(self) -> list[str]:
        held = self.params.get(self.organism_param or "")
        return [] if held is None else pick_terms(held)


@dataclass(frozen=True)
class _Reads:
    """The reads of one bind, each given what is left of the bind's budget."""

    counts: TurnCounts
    binding: MeasuredBinding
    bound: int
    deadline: float

    def _left(self) -> float:
        return max(self.deadline - asyncio.get_running_loop().time(), 0.0)

    async def count_with(self, values: Mapping[str, ParamValue]) -> int | None:
        """The records the binding answers with these values in place of its own."""
        b = self.binding
        return await self.counts.count(
            b.site_id,
            b.record_type,
            b.search_name,
            {**b.params, **values},
            timeout_seconds=self._left(),
        )

    async def reach(self, phrase: str) -> SiteSearchResponse | None:
        b = self.binding
        return await self.counts.reach(
            b.site_id, phrase, b.organisms(), timeout_seconds=self._left()
        )


def _at(value: ParamValue, reading: float) -> ParamValue | None:
    """The value the parameter sends at the reading, in the value's own kind."""
    match value:
        case NumberValue():
            return NumberValue(value=reading)
        case StringValue():
            return StringValue(value=NumberValue(value=reading).to_wire())
        case _:
            return None


def _bounds(value: ParamValue, info: ParameterInfo) -> list[tuple[ParamValue, str]]:
    """Each value the loosest bound may sit at, and how a reader is shown it.

    A range reads its published bounds whole; a number reads each published
    bound, and zero when the site publishes neither.
    """
    if info.param_kind == "number-range":
        if info.min is None or info.max is None:
            return []
        whole = param_value_from_raw({"min": info.min, "max": info.max}, "number-range")
        shown = f"{NumberValue(value=info.min).to_wire()} to "
        return [(whole, shown + NumberValue(value=info.max).to_wire())]
    bounds = [b for b in (info.min, info.max) if b is not None] or [_UNBOUNDED_READING]
    return [
        (at, NumberValue(value=bound).to_wire())
        for bound in bounds
        if (at := _at(value, bound)) is not None
    ]


async def _loosest_bound(
    reads: _Reads, name: str, value: ParamValue, info: ParameterInfo
) -> list[Measurement]:
    """The count at the bound that counts the most records, when it counts more.

    With no wider count, a bound whose count did not arrive is recorded unmeasured.
    """
    bounds = _bounds(value, info)
    counted = await asyncio.gather(*(reads.count_with({name: at}) for at, _ in bounds))
    read = list(zip(counted, (shown for _, shown in bounds), strict=True))
    wider = [(c, shown) for c, shown in read if c is not None and c > reads.bound]
    if wider:
        count, shown = max(wider, key=lambda pair: pair[0])
        return [
            Measurement(kind="loosest_bound", param=name, count=count, reading=shown)
        ]
    unread = [shown for c, shown in read if c is None]
    return [
        Measurement(kind="loosest_bound", param=name, reading=shown)
        for shown in unread[:1]
    ]


def _phrase(value: ParamValue) -> str | None:
    """The text when it is quoted or holds several words, else None."""
    match value:
        case StringValue(value=text) if len(text.split()) > 1 or (
            len(text) > 1 and text.startswith('"') and text.endswith('"')
        ):
            return text
        case _:
            return None


async def _text_readings(
    reads: _Reads, name: str, value: ParamValue
) -> list[Measurement]:
    """The site search's count of the phrase, and the count of its wildcard form.

    Only the search the site search hands its record type to reads the site
    search's grammar. That search reads no wildcard inside quotes, so only a
    single word has a wildcard form.
    """
    phrase = _phrase(value)
    if phrase is None:
        return [_not_measurable(name, "an unquoted single word is counted as written")]
    answer = await reads.reach(phrase)
    if answer is None:
        return [Measurement(kind="site_search_reach", param=name, reading=phrase)]
    bridged = next(
        (
            kind
            for kind in answer.document_types
            if kind.wdk_search_name == reads.binding.search_name
        ),
        None,
    )
    if bridged is None:
        return [_not_measurable(name, "the site search does not read this search")]
    found = [
        Measurement(
            kind="site_search_reach", param=name, count=bridged.count, reading=phrase
        )
    ]
    words = phrase.strip('"').split()
    if len(words) == 1 and not words[0].endswith("*"):
        wildcard = f"{words[0]}*"
        count = await reads.count_with({name: StringValue(value=wildcard)})
        found.append(
            Measurement(
                kind="wildcard_phrase", param=name, count=count, reading=wildcard
            )
        )
    return found


async def _phrase_reading(
    reads: _Reads, name: str, value: ParamValue
) -> list[Measurement]:
    """The count of a text with each operand of several words quoted.

    The text as sent matches any of its words, so the bind's own count is
    the words reading and this is the phrase reading, whoever wrote the text.
    """
    match value:
        case StringValue(value=text):
            quoted = TextExpression(text=text).phrase_reading()
        case _:
            quoted = None
    if quoted is None:
        return []
    count = await reads.count_with({name: StringValue(value=quoted)})
    return [
        Measurement(kind="wildcard_phrase", param=name, count=count, reading=quoted)
    ]


async def _stated_reading(reads: _Reads, name: str, stated: str) -> list[Measurement]:
    """The count of the request's phrase a chosen text leaves words out of."""
    count = await reads.count_with({name: StringValue(value=stated)})
    return [
        Measurement(kind="wildcard_phrase", param=name, count=count, reading=stated)
    ]


def _not_measurable(name: str, reason: str) -> Measurement:
    return Measurement(kind="not_measurable", param=name, reading=reason)


def _as_values(derived: PhyleticBinding) -> dict[str, ParamValue]:
    return {name: StringValue(value=v) for name, v in derived.model_dump().items()}


async def _strain_readings(
    reads: _Reads, value: ParamValue, tree: PhyleticTree
) -> list[Measurement]:
    """A species group required in every member, against at least one member.

    A census holds each species present or absent, so the genes with at least
    one member present are the genes with no constraint on the group less the
    genes with every member absent. Either count missing leaves it unmeasured.
    """
    binding = reads.binding
    excluded = binding.params.get(_EXCLUDED_SPECIES)
    excluded_codes = tree.resolve_terms(to_wire(excluded) if excluded else "").codes
    included_codes = tree.resolve_terms(to_wire(value)).codes
    states = tree.leaf_states(included_codes, excluded_codes)
    group = sorted(code for code, state in states.items() if state == "include")
    if len(group) < _SMALLEST_GROUP:
        return []
    free = derive_binding(tree, [], excluded_codes)
    absent = derive_binding(tree, [], [*excluded_codes, *group])
    found: list[Measurement] = []
    if isinstance(free, PhyleticBinding) and isinstance(absent, PhyleticBinding):
        without, none = await asyncio.gather(
            reads.count_with(_as_values(free)),
            reads.count_with(_as_values(absent)),
        )
        found.append(
            Measurement(
                kind="any_strain",
                param=_INCLUDED_SPECIES,
                count=None if without is None or none is None else without - none,
                reading=f"at least one of {len(group)} species",
            )
        )
    found.append(
        Measurement(
            kind="all_strains",
            param=_INCLUDED_SPECIES,
            count=reads.bound,
            reading=f"all {len(group)} species",
        )
    )
    return found


async def _excluded_reading(
    reads: _Reads, name: str, value: ParamValue, tree: PhyleticTree
) -> list[Measurement]:
    """The count with no species excluded, when it counts more."""
    included = reads.binding.params.get(_INCLUDED_SPECIES)
    included_codes = tree.resolve_terms(to_wire(included) if included else "").codes
    if not tree.resolve_terms(to_wire(value)).codes:
        return []
    match derive_binding(tree, included_codes, []):
        case PhyleticBinding() as free:
            count = await reads.count_with(_as_values(free))
        case _:
            return []
    if count is not None and count <= reads.bound:
        return []
    return [
        Measurement(
            kind="loosest_bound", param=name, count=count, reading="no species excluded"
        )
    ]


async def _species_readings(
    reads: _Reads, name: str, value: ParamValue, tree: PhyleticTree | None
) -> list[Measurement]:
    if tree is None:
        return [_not_measurable(name, "the search carries no species tree")]
    if name == _INCLUDED_SPECIES:
        return await _strain_readings(reads, value, tree)
    return await _excluded_reading(reads, name, value, tree)


async def _readings_of(
    reads: _Reads, info: ParameterInfo, value: ParamValue, tree: PhyleticTree | None
) -> list[Measurement]:
    rules = rules_of(info)
    match rules.measurement:
        case "species_lists":
            return await _species_readings(reads, info.name, value, tree)
        case "loosest_bound":
            return await _loosest_bound(reads, info.name, value, info)
        case "phrase_reach":
            return await _text_readings(reads, info.name, value)
        case "site_default":
            return await default_reading(
                reads.count_with, info.name, value, info, reads.bound
            )
        case "not_measurable":
            return [_not_measurable(info.name, rules.reason)]
        case "site_fixed":
            return []


def _unread(info: ParameterInfo, value: ParamValue) -> list[Measurement]:
    """A value whose binding counted nothing has no count to read another
    reading against."""
    unread = Measurement(kind="bound_count", param=info.name, reading=to_wire(value))
    match rules_of(info).measurement:
        case "site_fixed":
            return []
        case _:
            return [unread, *tree_note(info.name, info)]


def _has_readings(info: ParameterInfo, value: ParamValue) -> bool:
    """A text that states nothing has no other reading."""
    return rules_of(info).measurement != "phrase_reach" or text_query(info, value)


async def measure_binding(
    counts: TurnCounts,
    binding: MeasuredBinding,
    *,
    values: Mapping[str, BoundValue],
    infos: Sequence[ParameterInfo],
    tree: PhyleticTree | None = None,
) -> list[Measurement]:
    """The counts of the other readings of each value the site or the model set,
    all read within one budget.

    ``tree`` is the search's species tree, None for a search with none. A
    binding whose own count did not arrive records each such value unmeasured.
    """
    by_name = {info.name: info for info in infos}
    measured = {
        name: bound.value
        for name, bound in values.items()
        if name in by_name
        and bound.source in _MEASURED_SOURCES
        and _has_readings(by_name[name], bound.value)
    }
    if binding.count is None:
        return [m for name, v in measured.items() for m in _unread(by_name[name], v)]
    deadline = asyncio.get_running_loop().time() + MEASUREMENT_BUDGET_SECONDS
    reads = _Reads(counts, binding, binding.count, deadline)
    phrased = {
        name: bound.value
        for name, bound in values.items()
        if name in by_name and text_query(by_name[name], bound.value)
    }
    stated = {
        name: bound.stated_as
        for name, bound in values.items()
        if name in phrased and bound.stated_as
    }
    read = await asyncio.gather(
        *(_readings_of(reads, by_name[name], v, tree) for name, v in measured.items()),
        *(_phrase_reading(reads, name, v) for name, v in phrased.items()),
        *(_stated_reading(reads, name, text) for name, text in stated.items()),
    )
    return [measurement for group in read for measurement in group]
