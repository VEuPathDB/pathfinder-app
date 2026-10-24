"""One built step's records counted by each value of one column, with the tool
server's ``byValue`` count or the column's word cloud, and the columns a step
can be counted by."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from veupathdb.errors import DataParsingError, WDKError
from veupathdb.wdk import (
    ColumnNotCountableError,
    StrategyAPI,
    WDKAttributeField,
    get_strategy_api,
)
from veupathdb_mcp.catalog import genome_names, get_raw_record_types
from veupathdb_mcp.wdk import (
    ColumnCounts,
    ColumnNotCountedError,
    StepColumns,
    count_by_column,
    list_step_columns,
)

from pathfinder.domain.tally_facts import tally_id
from pathfinder.services.experiment.column_tally import (
    BY_VALUE,
    ColumnTally,
    ColumnTallyRefusedError,
    field_label,
    tally_title,
)
from pathfinder.services.experiment.tally_rows import (
    TallyRow,
    counted_rows,
    shown_text,
    sorted_rows,
)

_WORD_CLOUD = "wordCloud"
_GENOME_CODE_COLUMNS = frozenset({"abbreviation"})
_NAMED_COLUMNS = 20
_LISTED = "The step_columns tool lists the columns this step can be counted by."
_NONE_OTHER = "No other column of these records can be counted."
_SERVER_ERROR = 500


@dataclass(frozen=True)
class CountedStep:
    site_id: str
    wdk_step_id: int
    record_type: str
    search_name: str
    record_noun: str
    step_url: str | None
    refused: frozenset[str] = frozenset()

    @property
    def name(self) -> str:
        return f"step {self.wdk_step_id}"


@dataclass(frozen=True)
class _Counts:
    rows: list[TallyRow]
    total: int
    distinct: int
    label: str


def _by_value_report(field: WDKAttributeField) -> bool:
    return BY_VALUE in field.tools.reports


def _by_codes(fields: Sequence[WDKAttributeField]) -> frozenset[str]:
    return frozenset(
        f.name
        for f in fields
        if f.name in _GENOME_CODE_COLUMNS
        and not _by_value_report(f)
        and f.format_named(_WORD_CLOUD) is not None
    )


def _named(names: Sequence[str]) -> str:
    if not names:
        return _NONE_OTHER
    shown = ", ".join(names[:_NAMED_COLUMNS])
    more = len(names) - _NAMED_COLUMNS
    if more <= 0:
        return f"The columns it can be counted by: {shown}."
    return f"The columns it can be counted by: {shown}, and {more:,} more. {_LISTED}"


def _labelled(rows: list[TallyRow], names: dict[str, str]) -> list[TallyRow]:
    if not rows or not all(row.value in names for row in rows):
        return rows
    return [row.model_copy(update={"label": names[row.value]}) for row in rows]


def _counted_rows(counted: ColumnCounts) -> list[TallyRow]:
    if counted.kind == "number":
        return [
            TallyRow(value=shown_text(b.bin_label or b.bin_start), count=b.value)
            for b in counted.bins
        ]
    return counted_rows((v.value, v.count) for v in counted.values)


async def _counted(
    step: CountedStep, column: str, top: int, by_codes: frozenset[str]
) -> ColumnCounts:
    try:
        return await count_by_column(step.site_id, step.wdk_step_id, column, top)
    except ColumnNotCountedError as refused:
        why = (
            "it is not a column of the step"
            if refused.data_type is None
            else f"the site has no count of its {refused.data_type} values"
        )
        offered = sorted({*refused.countable, *by_codes} - step.refused - {column})
        msg = (
            f"{step.record_noun} records of {step.name} cannot be counted by "
            f"{column}: {why}. {_named(offered)}"
        )
        raise ColumnTallyRefusedError(msg) from refused
    except WDKError as refused:
        if refused.status >= _SERVER_ERROR:
            raise
        msg = (
            f"The site refused to count {column} on {step.name} "
            f"(HTTP {refused.status}). {_LISTED}"
        )
        raise ColumnTallyRefusedError(msg) from refused


async def _by_value(
    step: CountedStep, column: str, top: int, by_codes: frozenset[str]
) -> _Counts:
    counted = await _counted(step, column, top, by_codes)
    rows = _counted_rows(counted)
    if not rows and counted.total_records > 0:
        msg = (
            f"None of the {counted.total_records:,} {step.record_noun} records of "
            f"{step.name} has a value for {column} ({counted.display_name}), so it "
            f"counts nothing. {_LISTED}"
        )
        raise ColumnTallyRefusedError(msg)
    names = await genome_names(step.site_id) if rows else {}
    distinct = len(rows) if counted.kind == "number" else counted.distinct_values
    return _Counts(
        rows=_labelled(rows, names),
        total=counted.total_records,
        distinct=distinct or len(rows),
        label=counted.display_name,
    )


async def _by_words(
    api: StrategyAPI,
    step: CountedStep,
    field: WDKAttributeField,
    reporter: str,
    top: int,
) -> _Counts:
    label = f"{field.name} ({field_label(field)})"
    try:
        counts = await api.get_step_word_counts(step.wdk_step_id, reporter)
    except DataParsingError as unread:
        msg = (
            f"{label} cannot be counted on {step.name}: the site's word cloud "
            f"answered no counts ({unread.detail}). {_LISTED}"
        )
        raise ColumnTallyRefusedError(msg) from unread
    names = await genome_names(step.site_id)
    unknown = [tag.word for tag in counts.tags if tag.word not in names]
    if unknown:
        msg = (
            f"{label} cannot be counted on {step.name}: the site counts it only by "
            "its word cloud, which splits and folds values into words, so its counts "
            "are taken only when every word is a genome code, and "
            f"{', '.join(unknown[:3])} {'is' if len(unknown) == 1 else 'are'} not. "
            f"{_LISTED}"
        )
        raise ColumnTallyRefusedError(msg)
    total = await api.get_step_count(step.wdk_step_id)
    try:
        by_word = counts.record_counts(total)
    except ColumnNotCountableError as refused:
        msg = (
            f"{label} cannot count the {total:,} {step.record_noun} records of "
            f"{step.name}: its genome codes sum to {counts.total:,}, so some records "
            f"hold no code or more than one. {_LISTED}"
        )
        raise ColumnTallyRefusedError(msg) from refused
    rows = sorted_rows(TallyRow(value=w, count=n) for w, n in by_word.items())
    return _Counts(
        rows=_labelled(rows, names)[:top],
        total=total,
        distinct=len(rows),
        label=field_label(field),
    )


async def _record_fields(site_id: str, record_type: str) -> list[WDKAttributeField]:
    held = await get_raw_record_types(site_id)
    info = next((r for r in held if record_type in (r.url_segment, r.full_name)), None)
    return [] if info is None else info.attributes or []


async def run_step_tally(step: CountedStep, column: str, top: int) -> ColumnTally:
    fields = await _record_fields(step.site_id, step.record_type)
    field = next((f for f in fields if f.name == column), None)
    reporter = None if field is None else field.format_named(_WORD_CLOUD)
    by_codes = _by_codes(fields)
    if field is not None and reporter is not None and not _by_value_report(field):
        if column not in by_codes:
            msg = (
                f"{field.name} ({field_label(field)}) cannot be counted on "
                f"{step.name}: the site counts it only by its word cloud, which "
                "splits and folds values into words, so only a column of genome "
                f"codes is counted that way. {_LISTED}"
            )
            raise ColumnTallyRefusedError(msg)
        api = get_strategy_api(step.site_id)
        counts = await _by_words(api, step, field, reporter, top)
    else:
        counts = await _by_value(step, column, top, by_codes)
    return ColumnTally(
        id=tally_id(step.site_id, step.name, column, None),
        title=tally_title(step.record_noun, counts.label, "", None),
        search_name=step.search_name,
        record_type=step.record_type,
        record_noun=step.record_noun,
        column=column,
        column_label=counts.label,
        total=counts.total,
        distinct=counts.distinct,
        rows=counts.rows,
        site_id=step.site_id,
        step_url=step.step_url,
    )


async def countable_columns(site_id: str, wdk_step_id: int) -> StepColumns:
    listed = await list_step_columns(site_id, wdk_step_id)
    by_codes = _by_codes(await _record_fields(site_id, listed.record_type))
    columns = tuple(
        c.model_copy(update={"countable": True}) if c.name in by_codes else c
        for c in listed.columns
    )
    return listed.model_copy(update={"columns": columns})
