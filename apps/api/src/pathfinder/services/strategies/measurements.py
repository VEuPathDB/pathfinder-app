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
    PhyleticTree,
    StringValue,
    param_value_from_raw,
    to_wire,
)
from veupathdb.errors import VEuPathDBError, WDKError
from veupathdb.wdk import SiteSearchResponse, get_site_router
from veupathdb_mcp.catalog import ParameterInfo
from veupathdb_mcp.wdk import count_search_answer

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    CountedKind,
    Measurement,
)
from pathfinder.domain.strategy.text_expression import TextExpression
from pathfinder.services.strategies.parameter_rules import rules_of, text_query
from pathfinder.services.strategies.pick_readings import default_reading, tree_note
from pathfinder.services.strategies.slow_searches import counts_slowly, timed
from pathfinder.services.strategies.species_readings import species_readings
from pathfinder.services.strategies.value_labels import pick_terms

logger = get_logger(__name__)

CountKey = tuple[str, str, str, str]
ReachKey = tuple[str, str, tuple[str, ...]]

_MEASURED_SOURCES = frozenset({"default", "chosen"})
# A number the site publishes no bound for is read at zero.
_UNBOUNDED_READING = 0.0
# Each reading of a bind, apart from the bind's own count, has this long once it
# is sent; a reading that has not arrived by then is recorded as not measured.
MEASUREMENT_BUDGET_SECONDS = 20.0
_SLOW_SEARCH = "the site counts this search too slowly to count its other readings"


@dataclass
class TurnCounts:
    """The counts and the site-search answers one turn read.

    A count that did not arrive is not held, so a later reading asks again.
    """

    counts: dict[CountKey, int] = field(default_factory=dict)
    reaches: dict[ReachKey, SiteSearchResponse] = field(default_factory=dict)
    pending: dict[CountKey, asyncio.Task[int | None]] = field(default_factory=dict)

    @staticmethod
    def _key(
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
    ) -> CountKey:
        config = json.dumps(
            {name: to_wire(value) for name, value in params.items()}, sort_keys=True
        )
        return (site_id, record_type, search_name, config)

    def remember(
        self,
        site_id: str,
        record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
        count: int,
    ) -> None:
        self.counts[self._key(site_id, record_type, search_name, params)] = count

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
        key = self._key(site_id, record_type, search_name, params)
        if key in self.counts:
            return self.counts[key]
        if key not in self.pending:
            self.pending[key] = asyncio.create_task(
                self._ask(key, params, timeout_seconds=timeout_seconds)
            )
        return await self.pending[key]

    async def _ask(
        self,
        key: CountKey,
        params: Mapping[str, ParamValue],
        *,
        timeout_seconds: float,
    ) -> int | None:
        site_id, record_type, search_name, _ = key
        try:
            counted = await timed(
                site_id,
                search_name,
                count_search_answer(
                    site_id,
                    record_type,
                    search_name,
                    params,
                    timeout_seconds=timeout_seconds,
                ),
            )
        except WDKError as exc:
            logger.warning("Count did not answer", site_id=site_id, error=str(exc))
            return None
        finally:
            self.pending.pop(key, None)
        if counted is not None:
            self.counts[key] = counted
        return counted

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
    """The reads of one bind, each given the measurement budget once it is sent."""

    counts: TurnCounts
    binding: MeasuredBinding
    bound: int

    async def count_with(self, values: Mapping[str, ParamValue]) -> int | None:
        """The records the binding answers with these values in place of its own."""
        b = self.binding
        return await self.counts.count(
            b.site_id,
            b.record_type,
            b.search_name,
            {**b.params, **values},
            timeout_seconds=MEASUREMENT_BUDGET_SECONDS,
        )

    async def reach(self, phrase: str) -> SiteSearchResponse | None:
        b = self.binding
        return await self.counts.reach(
            b.site_id,
            phrase,
            b.organisms(),
            timeout_seconds=MEASUREMENT_BUDGET_SECONDS,
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
    """The site search's count of the phrase, the count of its wildcard form,
    and the count of each quoted phrase as its words.

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
    unquoted = TextExpression(text=phrase).words_reading()
    if unquoted is not None:
        found.extend(await _counted_text(reads, name, "words_reading", unquoted))
    return found


def _quoted(value: ParamValue) -> str | None:
    """The text with each operand of several words quoted, else None.

    The text as sent matches any of its words, so the bind's own count is the
    words reading and this is the phrase reading, whoever wrote the text.
    """
    match value:
        case StringValue(value=text):
            return TextExpression(text=text).phrase_reading()
        case _:
            return None


async def _counted_text(
    reads: _Reads, name: str, kind: CountedKind, text: str
) -> list[Measurement]:
    """The count of the binding with this text in place of its own."""
    count = await reads.count_with({name: StringValue(value=text)})
    return [Measurement(kind=kind, param=name, count=count, reading=text)]


def _not_measurable(name: str, reason: str) -> Measurement:
    return Measurement(kind="not_measurable", param=name, reading=reason)


async def _species_readings(
    reads: _Reads, name: str, value: ParamValue, tree: PhyleticTree | None
) -> list[Measurement]:
    if tree is None:
        return [_not_measurable(name, "the search carries no species tree")]
    return await species_readings(
        reads.count_with, reads.binding.params, reads.bound, name, value, tree
    )


async def _readings_of(
    reads: _Reads, info: ParameterInfo, held: BoundValue, tree: PhyleticTree | None
) -> list[Measurement]:
    value = held.value
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
                reads.count_with, info.name, held, info, reads.bound
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


def _has_readings(info: ParameterInfo, held: BoundValue) -> bool:
    """A placeholder, and a text that states nothing, have no other reading."""
    if held.placeholder:
        return False
    return rules_of(info).measurement != "phrase_reach" or text_query(info, held)


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
        name: bound
        for name, bound in values.items()
        if name in by_name
        and bound.source in _MEASURED_SOURCES
        and _has_readings(by_name[name], bound)
    }
    if binding.count is None:
        return [
            m for name, b in measured.items() for m in _unread(by_name[name], b.value)
        ]
    if counts_slowly(binding.site_id, binding.search_name):
        return [_not_measurable(name, _SLOW_SEARCH) for name in measured]
    counts.remember(
        binding.site_id,
        binding.record_type,
        binding.search_name,
        binding.params,
        binding.count,
    )
    reads = _Reads(counts, binding, binding.count)
    quoted = {
        name: text
        for name, bound in values.items()
        if name in by_name
        and text_query(by_name[name], bound)
        and (text := _quoted(bound.value)) is not None
    }
    read = await asyncio.gather(
        *(_readings_of(reads, by_name[name], v, tree) for name, v in measured.items()),
        *(
            _counted_text(reads, name, "phrase_reading", text)
            for name, text in quoted.items()
        ),
    )
    return [measurement for group in read for measurement in group]
