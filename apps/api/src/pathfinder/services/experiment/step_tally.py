"""One built step's records counted by each value of one column, with the site's
``byValue`` column reporter or the column's word cloud, in one request."""

from __future__ import annotations

from dataclasses import dataclass

from veupathdb.errors import DataParsingError, WDKError
from veupathdb.wdk import (
    ColumnNotCountableError,
    StrategyAPI,
    WDKAttributeField,
    get_strategy_api,
)
from veupathdb_mcp.catalog import genome_names

from pathfinder.domain.tally_facts import tally_id
from pathfinder.services.experiment.column_tally import (
    BY_VALUE,
    ColumnTally,
    ColumnTallyRefusedError,
    field_label,
    tally_title,
)
from pathfinder.services.experiment.tally_rows import (
    KEPT_ROWS,
    TallyRow,
    distribution_rows,
    sorted_rows,
)

_WORD_CLOUD = "wordCloud"
_GENOME_CODE_COLUMNS = frozenset({"abbreviation"})


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
    missing: int = 0


def _by_value_report(field: WDKAttributeField) -> bool:
    return BY_VALUE in field.tools.reports


def _counted_by_codes(field: WDKAttributeField) -> bool:
    return (
        field.name in _GENOME_CODE_COLUMNS
        and field.format_named(_WORD_CLOUD) is not None
    )


def _countable(field: WDKAttributeField) -> bool:
    return _by_value_report(field) or _counted_by_codes(field)


def _named(fields: list[WDKAttributeField]) -> str:
    return ", ".join(f"{f.name} ({field_label(f)})" for f in fields)


_BY_WORDS = "The columns counted by their word cloud when every value is a genome code"


def _offered(fields: list[WDKAttributeField], excluded: frozenset[str]) -> str:
    others = [f for f in fields if _countable(f) and f.name not in excluded]
    by_value = _named([f for f in others if _by_value_report(f)])
    by_words = _named([f for f in others if not _by_value_report(f)])
    sentences = [
        f"{heading}: {named}."
        for heading, named in (
            ("The columns the site counts by value", by_value),
            (_BY_WORDS, by_words),
        )
        if named
    ]
    return " ".join(sentences) or "No other column of these records can be counted."


def _labelled(rows: list[TallyRow], names: dict[str, str]) -> list[TallyRow]:
    if not rows or not all(row.value in names for row in rows):
        return rows
    return [row.model_copy(update={"label": names[row.value]}) for row in rows]


async def _by_value(
    api: StrategyAPI, step: CountedStep, field: WDKAttributeField, offered: str
) -> _Counts:
    label = f"{field.name} ({field_label(field)})"
    try:
        distribution = await api.get_column_distribution(step.wdk_step_id, field.name)
    except WDKError as refused:
        msg = (
            f"The site refused to count {label} on {step.name} "
            f"(HTTP {refused.status}). {offered}"
        )
        raise ColumnTallyRefusedError(msg) from refused
    rows = distribution_rows(distribution)
    stats = distribution.statistics
    if not rows and stats.subset_size > 0:
        msg = (
            f"None of the {stats.subset_size:,} {step.record_noun} records of "
            f"{step.name} has a value for {label}, so it counts nothing. {offered}"
        )
        raise ColumnTallyRefusedError(msg)
    names = await genome_names(step.site_id) if rows else {}
    return _Counts(
        rows=_labelled(rows, names),
        total=stats.subset_size,
        distinct=stats.num_distinct_values or len(rows),
        missing=stats.num_missing_cases,
    )


async def _by_words(
    api: StrategyAPI,
    step: CountedStep,
    field: WDKAttributeField,
    reporter: str,
    offered: str,
) -> _Counts:
    label = f"{field.name} ({field_label(field)})"
    try:
        counts = await api.get_step_word_counts(step.wdk_step_id, reporter)
    except DataParsingError as unread:
        msg = (
            f"{label} cannot be counted on {step.name}: the site's word cloud "
            f"answered no counts ({unread.detail}). {offered}"
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
            f"{offered}"
        )
        raise ColumnTallyRefusedError(msg)
    total = await api.get_step_count(step.wdk_step_id)
    try:
        by_word = counts.record_counts(total)
    except ColumnNotCountableError as refused:
        msg = (
            f"{label} cannot count the {total:,} {step.record_noun} records of "
            f"{step.name}: its genome codes sum to {counts.total:,}, so some records "
            f"hold no code or more than one. {offered}"
        )
        raise ColumnTallyRefusedError(msg) from refused
    rows = sorted_rows(TallyRow(value=w, count=n) for w, n in by_word.items())
    return _Counts(rows=_labelled(rows, names), total=total, distinct=len(rows))


async def run_step_tally(step: CountedStep, column: str) -> ColumnTally:
    api = get_strategy_api(step.site_id)
    fields = (await api.get_record_type_info(step.record_type)).attributes or []
    field = next((f for f in fields if f.name == column), None)
    offered = _offered(fields, step.refused | {column})
    reporter = None if field is None else field.format_named(_WORD_CLOUD)
    if field is None or (not _by_value_report(field) and reporter is None):
        msg = f"{step.record_noun} records cannot be counted by {column}. {offered}"
        raise ColumnTallyRefusedError(msg)
    if not _countable(field):
        msg = (
            f"{field.name} ({field_label(field)}) cannot be counted on {step.name}: "
            "the site counts it only by its word cloud, which splits and folds "
            "values into words, so only a column of genome codes is counted that "
            f"way. {offered}"
        )
        raise ColumnTallyRefusedError(msg)
    counts = (
        await _by_value(api, step, field, offered)
        if _by_value_report(field) or reporter is None
        else await _by_words(api, step, field, reporter, offered)
    )
    return ColumnTally(
        id=tally_id(step.site_id, step.name, column, None),
        title=tally_title(step.record_noun, field, "", None),
        search_name=step.search_name,
        record_type=step.record_type,
        record_noun=step.record_noun,
        column=column,
        column_label=field_label(field),
        total=counts.total,
        distinct=counts.distinct,
        missing=counts.missing,
        rows=counts.rows[:KEPT_ROWS],
        site_id=step.site_id,
        step_url=step.step_url,
    )
