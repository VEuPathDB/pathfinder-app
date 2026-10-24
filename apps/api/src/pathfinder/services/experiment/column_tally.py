"""One search's records counted by each value of one column, with the site's
``byValue`` column reporter, after the rows another column keeps."""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb import JSONObject, JSONValue
from veupathdb.domain.parameters import wire_map
from veupathdb.wdk import (
    WDKAttributeField,
    WDKSearchConfig,
    get_strategy_api,
    get_wdk_client,
)
from veupathdb.wdk.wdk_models import WDKColumnDistribution

from pathfinder.domain.tally_facts import TallyFact, TallyRowFact, tally_id
from pathfinder.services.experiment.tally_rows import (
    KEPT_ROWS,
    TallyRow,
    distribution_rows,
    shown_value,
)
from pathfinder.services.experiment.variant_comparison import VariantSpec

BY_VALUE = "byValue"


class ColumnTallyRefusedError(ValueError):
    """The site offers no count or no filter on the column named."""


class TallyOnly(CamelModel):
    column: str
    values: list[str]


class ColumnTally(CamelModel):
    id: str
    title: str
    search_name: str
    record_type: str
    record_noun: str
    column: str
    column_label: str
    only: TallyOnly | None = None
    only_label: str = ""
    total: int
    distinct: int
    rows: list[TallyRow] = Field(default_factory=list)
    site_id: str
    step_url: str | None = None

    def fact(self) -> TallyFact:
        return TallyFact(
            id=self.id,
            title=self.title,
            record_noun=self.record_noun,
            total=self.total,
            distinct=self.distinct,
            rows=[TallyRowFact(value=row.value, count=row.count) for row in self.rows],
        )


type _Tool = Literal["reports", "filters"]


def _offers(field: WDKAttributeField, tool: _Tool) -> bool:
    return BY_VALUE in (
        field.tools.reports if tool == "reports" else field.tools.filters
    )


def _offered(
    fields: list[WDKAttributeField], name: str, tool: _Tool, noun: str
) -> WDKAttributeField:
    field = next((f for f in fields if f.name == name), None)
    kind = "counted" if tool == "reports" else "kept"
    if field is not None and _offers(field, tool):
        return field
    offered = ", ".join(
        f"{f.name} ({f.display_name})" for f in fields if _offers(f, tool)
    )
    msg = (
        f"{noun} records cannot be {kind} by {name}. The columns they can be "
        f"{kind} by: {offered}."
    )
    raise ColumnTallyRefusedError(msg)


def field_label(field: WDKAttributeField) -> str:
    return field.display_name or field.name


def tally_title(noun: str, column: str, kept: str, only: TallyOnly | None) -> str:
    title = f"{noun.capitalize()}s by {column}"
    if only is None:
        return title
    return f"{title}, where {kept} is {' or '.join(only.values)}"


async def _distribution(
    site_id: str, spec: VariantSpec, column: str, filters: JSONObject | None
) -> WDKColumnDistribution:
    return await get_wdk_client(site_id).run_search_column_report(
        spec.record_type,
        spec.search_name,
        WDKSearchConfig(parameters=wire_map(spec.parameters), column_filters=filters),
        column,
    )


async def _stored_values(
    site_id: str, spec: VariantSpec, kept: WDKAttributeField, only: TallyOnly, noun: str
) -> list[str]:
    held = await _distribution(site_id, spec, kept.name, None)
    stored = {shown_value(b): b.bin_start for b in held.histogram if shown_value(b)}
    stored |= {b.bin_start: b.bin_start for b in held.histogram if shown_value(b)}
    unheld = [value for value in only.values if value not in stored]
    if unheld:
        values = ", ".join(row.value for row in distribution_rows(held)[:KEPT_ROWS])
        msg = (
            f"No {noun} record has {kept.name} ({field_label(kept)}) "
            f"{' or '.join(unheld)}. The values {kept.name} holds: {values}."
        )
        raise ColumnTallyRefusedError(msg)
    return [stored[value] for value in only.values]


async def run_column_tally(
    site_id: str,
    spec: VariantSpec,
    column: str,
    only: TallyOnly | None,
    *,
    record_noun: str,
) -> ColumnTally:
    """The search's records counted by each value of the column, most first,
    after the rows ``only`` keeps. Refuses a column the site counts no records
    by, a column it keeps no rows by, a filter value the column does not hold
    and a column no record kept has a value for."""
    info = await get_strategy_api(site_id).get_record_type_info(spec.record_type)
    fields = info.attributes or []
    counted = _offered(fields, column, "reports", record_noun)
    kept = (
        None if only is None else _offered(fields, only.column, "filters", record_noun)
    )
    filters: JSONObject | None = None
    if only is not None and kept is not None:
        stored: list[JSONValue] = list(
            await _stored_values(site_id, spec, kept, only, record_noun)
        )
        filters = {only.column: {BY_VALUE: {"values": stored}}}
    distribution = await _distribution(site_id, spec, column, filters)
    stats = distribution.statistics
    rows = distribution_rows(distribution)
    if not rows and stats.subset_size > 0:
        msg = (
            f"None of the {stats.subset_size:,} {record_noun} records has a value "
            f"for {column} ({field_label(counted)}), so it counts nothing. Count them "
            "by another column."
        )
        raise ColumnTallyRefusedError(msg)
    only_label = "" if kept is None else field_label(kept)
    return ColumnTally(
        id=tally_id(
            site_id,
            spec.search_name,
            column,
            None if only is None else (only.column, tuple(only.values)),
        ),
        title=tally_title(record_noun, field_label(counted), only_label, only),
        search_name=spec.search_name,
        record_type=spec.record_type,
        record_noun=record_noun,
        column=column,
        column_label=field_label(counted),
        only=only,
        only_label=only_label,
        total=stats.subset_size,
        distinct=stats.num_distinct_values or len(rows),
        rows=rows[:KEPT_ROWS],
        site_id=site_id,
    )
