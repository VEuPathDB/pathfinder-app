"""One search's records counted by each value of one column, with the site's
``byValue`` column reporter, after the rows another column keeps."""

from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb import JSONObject, strip_html_tags
from veupathdb.domain.parameters import wire_map
from veupathdb.wdk import (
    WDKAttributeField,
    WDKSearchConfig,
    get_strategy_api,
    get_wdk_client,
)

from pathfinder.domain.tally_facts import TallyFact, TallyRowFact, tally_id
from pathfinder.services.experiment.variant_comparison import VariantSpec

_BY_VALUE = "byValue"
_KEPT_ROWS = 200


class ColumnTallyRefusedError(ValueError):
    """The site offers no count or no filter on the column named."""


class TallyOnly(CamelModel):
    column: str
    values: list[str]


class TallyRow(CamelModel):
    value: str
    count: int


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
    missing: int = 0
    rows: list[TallyRow] = Field(default_factory=list)

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
    return _BY_VALUE in (
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


def _title(
    noun: str, column: WDKAttributeField, kept: str, only: TallyOnly | None
) -> str:
    title = f"{noun.capitalize()}s by {column.display_name or column.name}"
    if only is None:
        return title
    return f"{title}, where {kept} is {' or '.join(only.values)}"


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
    by and a column it keeps no rows by."""
    info = await get_strategy_api(site_id).get_record_type_info(spec.record_type)
    fields = info.attributes or []
    counted = _offered(fields, column, "reports", record_noun)
    kept = (
        None if only is None else _offered(fields, only.column, "filters", record_noun)
    )
    filters: JSONObject | None = (
        None
        if only is None
        else {only.column: {_BY_VALUE: {"values": list(only.values)}}}
    )
    distribution = await get_wdk_client(site_id).run_search_column_report(
        spec.record_type,
        spec.search_name,
        WDKSearchConfig(parameters=wire_map(spec.parameters), column_filters=filters),
        column,
    )
    rows = sorted(
        (
            TallyRow(value=strip_html_tags(b.bin_label or b.bin_start), count=b.value)
            for b in distribution.histogram
        ),
        key=lambda row: (-row.count, row.value),
    )
    only_label = "" if kept is None else kept.display_name or kept.name
    stats = distribution.statistics
    return ColumnTally(
        id=tally_id(
            site_id,
            spec.search_name,
            column,
            None if only is None else (only.column, tuple(only.values)),
        ),
        title=_title(record_noun, counted, only_label, only),
        search_name=spec.search_name,
        record_type=spec.record_type,
        record_noun=record_noun,
        column=column,
        column_label=counted.display_name or column,
        only=only,
        only_label=only_label,
        total=stats.subset_size,
        distinct=stats.num_distinct_values or len(rows),
        missing=stats.num_missing_cases,
        rows=rows[:_KEPT_ROWS],
    )
