"""The checks an export clears before it becomes a strategy step."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import NumberValue, ParamValue, StringValue, to_wire
from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaDateRangeFilter,
    EdaFilter,
    EdaLongitudeRangeFilter,
    EdaNumberRangeFilter,
    EdaStudyDetail,
    differential_expression_computations,
)

from pathfinder.ai.tools.standalone._eda_sheet import sheet_entries
from pathfinder.domain.eda_parts import (
    EdaComparison,
    EdaEffectDirection,
    EdaFilterSheetEntry,
)
from pathfinder.domain.strategy.analysis_binding import SubsetBasis
from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.value_source import stated_words, value_source
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.compute import VolcanoThresholds, analysis_comparison
from pathfinder.services.eda.description import display_names, filter_summaries
from pathfinder.services.eda.export import exported_dataset

_CLASS_SIZE = 8
_CLASSES_OFFERED = 4


def refuse_a_direction_without_a_volcano(
    analysis: EdaAnalysisDetail,
    *,
    effect_direction: EdaEffectDirection | None,
    has_thresholds: bool,
) -> None:
    """A direction selects a side of a computed volcano, so it needs both."""
    if effect_direction is None:
        return
    if not differential_expression_computations(analysis.descriptor):
        msg = (
            f'effect_direction="{effect_direction}" selects a side of a '
            f"comparison, and the open analysis holds 0 comparisons. Nothing "
            f"was written. Call run_eda_compute to run the comparison, then "
            f"export with effect_size_threshold, significance_threshold and "
            f"effect_direction."
        )
        raise ModelRetry(msg)
    if not has_thresholds:
        msg = (
            f'effect_direction="{effect_direction}" selects a side of the '
            f"volcano, so it needs effect_size_threshold and "
            f"significance_threshold. Send both, or leave effect_direction unset "
            f"to export the subset. Nothing was written."
        )
        raise ModelRetry(msg)


def compared_groups(
    analysis: EdaAnalysisDetail, thresholds: VolcanoThresholds | None
) -> EdaComparison | None:
    """The groups a compute export compares. The subset export compares none."""
    if thresholds is None:
        return None
    return analysis_comparison(analysis)


def refuse_half_a_cut(
    effect_size_threshold: float | None,
    significance_threshold: float | None,
) -> None:
    """Both thresholds or neither. The bridge plugin requires both keys."""
    if effect_size_threshold is not None and significance_threshold is None:
        msg = (
            "A volcano export needs significance_threshold as well as "
            "effect_size_threshold. Send both, or send neither to export the "
            "whole subset."
        )
        raise ModelRetry(msg)
    if significance_threshold is not None and effect_size_threshold is None:
        msg = (
            "A volcano export needs effect_size_threshold as well as "
            "significance_threshold. Send both, or send neither to export the "
            "whole subset."
        )
        raise ModelRetry(msg)


def volcano_thresholds(
    analysis: EdaAnalysisDetail,
    effect_size_threshold: float | None,
    significance_threshold: float | None,
    effect_direction: EdaEffectDirection | None,
) -> VolcanoThresholds | None:
    """The volcano cut this call names, or None for the subset export."""
    has_thresholds = (
        effect_size_threshold is not None and significance_threshold is not None
    )
    refuse_a_direction_without_a_volcano(
        analysis, effect_direction=effect_direction, has_thresholds=has_thresholds
    )
    if effect_size_threshold is None or significance_threshold is None:
        return None
    return VolcanoThresholds(
        effect_size_threshold=effect_size_threshold,
        significance_threshold=significance_threshold,
        effect_direction=effect_direction or "upAndDown",
    )


def refuse_a_recut_of_another_dataset(
    graph: StrategyGraph, replace_step_id: str, dataset_id: str
) -> None:
    """An export reads the open analysis, so it takes no export of another
    dataset's place."""
    exported = exported_dataset(graph, replace_step_id)
    if exported is None or exported == dataset_id:
        return
    msg = (
        f"{replace_step_id} exports an analysis of dataset {exported}, and the open "
        f"analysis is on dataset {dataset_id}: an export reads the open analysis, "
        f"so it cannot take that step's place. Open the analysis on {exported} to "
        "recut it, or name a step this analysis exports."
    )
    raise ModelRetry(msg)


def _inside[T: (float, str)](value: T, low: T | None, high: T | None) -> bool:
    return (low is None or value > low) and (high is None or value < high)


def _date(text: str) -> str:
    return text.split("T", 1)[0]


def _cut_bounds(
    cut: EdaNumberRangeFilter | EdaDateRangeFilter, entry: EdaFilterSheetEntry | None
) -> list[ParamValue]:
    match cut:
        case EdaNumberRangeFilter(min=low, max=high):
            ends = (None, None) if entry is None else (entry.range_min, entry.range_max)
            return [NumberValue(value=b) for b in (low, high) if _inside(b, *ends)]
        case EdaDateRangeFilter(min=low, max=high):
            dates = (None, None) if entry is None else (entry.date_min, entry.date_max)
            first, last = (None if d is None else _date(d) for d in dates)
            return [
                StringValue(value=_date(b))
                for b in (low, high)
                if _inside(_date(b), first, last)
            ]


def _bound_source(
    value: ParamValue, name: str, said: Sequence[str], picks: Sequence[str]
) -> tuple[ValueSource, str]:
    picked = next((p for p in picks if stated_words(value, [p], display_name=name)), "")
    source = value_source(
        value,
        placeholder=False,
        unset=False,
        request_texts=said,
        card_value=to_wire(value) if picked else None,
        display_name=name,
    )
    return source, picked


def _span(entry: EdaFilterSheetEntry | None) -> str:
    if entry is None:
        return ""
    if entry.range_min is not None and entry.range_max is not None:
        return f" across its range {entry.range_min:g} to {entry.range_max:g}"
    if entry.date_min is not None and entry.date_max is not None:
        return f" across its range {entry.date_min} to {entry.date_max}"
    return ""


def _unstated_cut(
    shown: str,
    entry: EdaFilterSheetEntry | None,
    entries: Sequence[EdaFilterSheetEntry],
) -> ModelRetry:
    classes = [
        f"{e.display_name}: {', '.join(e.vocabulary)}"
        for e in entries
        if e.filter_type == "stringSet" and 0 < e.vocabulary_total <= _CLASS_SIZE
    ][:_CLASSES_OFFERED]
    offered = f"the study's own classes ({'; '.join(classes)}) and " if classes else ""
    return ModelRetry(
        f"{shown} is a cut no researcher message states and no card picked. "
        f"Nothing was written. Ask the researcher with consult_user, offering "
        f"{offered}a few cuts{_span(entry)}, each counted with preview_eda_subset."
    )


def _range_basis(
    cut: EdaNumberRangeFilter | EdaDateRangeFilter,
    shown: str,
    entries: Sequence[EdaFilterSheetEntry],
    said: Sequence[str],
    picks: Sequence[str],
) -> SubsetBasis | None:
    entry = next(
        (
            e
            for e in entries
            if (e.entity_id, e.variable_id) == (cut.entity_id, cut.variable_id)
        ),
        None,
    )
    name = cut.variable_id if entry is None else entry.display_name
    sources = [_bound_source(b, name, said, picks) for b in _cut_bounds(cut, entry)]
    if not sources:
        return None
    if any(source == "chosen" for source, _picked in sources):
        raise _unstated_cut(shown, entry, entries)
    picked = next((p for source, p in sources if source == "card"), "")
    if picked:
        return SubsetBasis(filter=shown, basis="card", picked=picked)
    return SubsetBasis(filter=shown, basis="stated")


def _filter_basis(
    each: EdaFilter,
    shown: str,
    entries: Sequence[EdaFilterSheetEntry],
    said: Sequence[str],
    picks: Sequence[str],
) -> SubsetBasis | None:
    match each:
        case EdaLongitudeRangeFilter():
            return None
        case EdaNumberRangeFilter() | EdaDateRangeFilter():
            return _range_basis(each, shown, entries, said, picks)
        case _:
            return SubsetBasis(filter=shown, basis="study")


def subset_basis(
    filters: Sequence[EdaFilter],
    study: EdaStudyDetail,
    *,
    said: Sequence[str],
    picks: Sequence[str],
) -> list[SubsetBasis]:
    entries = sheet_entries(study)
    shown = filter_summaries(filters, display_names=display_names(study))
    bases = [
        _filter_basis(each, summary, entries, said, picks)
        for each, summary in zip(filters, shown, strict=True)
    ]
    return [basis for basis in bases if basis is not None]


async def the_subset_basis(
    site_id: str,
    dataset_id: str,
    analysis: EdaAnalysisDetail,
    *,
    said: Sequence[str],
    picks: Sequence[str],
) -> list[SubsetBasis]:
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    return subset_basis(
        analysis.descriptor.subset.descriptor, study, said=said, picks=picks
    )
