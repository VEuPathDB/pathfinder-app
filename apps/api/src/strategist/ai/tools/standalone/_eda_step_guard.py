"""The checks an export clears before it becomes a strategy step."""

from __future__ import annotations

from collections.abc import Container, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

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

from strategist.ai.graph.thread_requirements import ThreadRequirements
from strategist.ai.tools.standalone._eda_sheet import sheet_entries
from strategist.ai.tools.standalone.eda_cut import (
    ask_sentence,
    cut_card,
    picked_rule_sentences,
)
from strategist.domain.eda_cut import TailEdge
from strategist.domain.eda_parts import (
    EdaComparison,
    EdaEffectDirection,
    EdaFilterSheetEntry,
)
from strategist.domain.strategy.analysis_binding import SubsetBasis
from strategist.domain.strategy.operational_spec import ValueSource
from strategist.domain.strategy.questions import OpenQuestion
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.value_source import stated_words, value_source
from strategist.services.eda.catalog import get_study_detail_for_dataset
from strategist.services.eda.compute import VolcanoThresholds, analysis_comparison
from strategist.services.eda.cut_offer import counted_noun, study_tail_edges
from strategist.services.eda.description import display_names, filter_summaries
from strategist.services.eda.export import exported_dataset


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


type _Side = Literal["min", "max"]


def _cut_bounds(
    cut: EdaNumberRangeFilter | EdaDateRangeFilter, entry: EdaFilterSheetEntry | None
) -> list[tuple[_Side, ParamValue]]:
    sides: tuple[_Side, _Side] = ("min", "max")
    match cut:
        case EdaNumberRangeFilter(min=low, max=high):
            ends = (None, None) if entry is None else (entry.range_min, entry.range_max)
            return [
                (side, NumberValue(value=b))
                for side, b in zip(sides, (low, high), strict=True)
                if _inside(b, *ends)
            ]
        case EdaDateRangeFilter(min=low, max=high):
            dates = (None, None) if entry is None else (entry.date_min, entry.date_max)
            first, last = (None if d is None else _date(d) for d in dates)
            return [
                (side, StringValue(value=_date(b)))
                for side, b in zip(sides, (low, high), strict=True)
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


@dataclass(frozen=True, slots=True)
class UnstatedCut:
    shown: str
    entity_id: str
    variable_id: str
    variable_name: str
    at_least: float | None
    at_most: float | None

    @property
    def numeric(self) -> bool:
        return self.at_least is not None or self.at_most is not None


def _unstated(
    cut: EdaNumberRangeFilter | EdaDateRangeFilter,
    shown: str,
    name: str,
    chosen: Container[str],
) -> UnstatedCut:
    match cut:
        case EdaNumberRangeFilter(min=low, max=high):
            at_least = low if "min" in chosen else None
            at_most = high if "max" in chosen else None
        case EdaDateRangeFilter():
            at_least = at_most = None
    return UnstatedCut(
        shown=shown,
        entity_id=cut.entity_id,
        variable_id=cut.variable_id,
        variable_name=name,
        at_least=at_least,
        at_most=at_most,
    )


def _range_basis(
    cut: EdaNumberRangeFilter | EdaDateRangeFilter,
    shown: str,
    entries: Sequence[EdaFilterSheetEntry],
    said: Sequence[str],
    picks: Sequence[str],
) -> SubsetBasis | UnstatedCut | None:
    entry = next(
        (
            e
            for e in entries
            if (e.entity_id, e.variable_id) == (cut.entity_id, cut.variable_id)
        ),
        None,
    )
    name = cut.variable_id if entry is None else entry.display_name
    sources = [
        (side, *_bound_source(b, name, said, picks))
        for side, b in _cut_bounds(cut, entry)
    ]
    if not sources:
        return None
    chosen = {side for side, source, _picked in sources if source == "chosen"}
    if chosen:
        return _unstated(cut, shown, name, chosen)
    picked = next((p for _side, source, p in sources if source == "card"), "")
    if picked:
        return SubsetBasis(filter=shown, basis="card", picked=picked)
    return SubsetBasis(filter=shown, basis="stated")


def _filter_basis(
    each: EdaFilter,
    shown: str,
    entries: Sequence[EdaFilterSheetEntry],
    said: Sequence[str],
    picks: Sequence[str],
) -> SubsetBasis | UnstatedCut | None:
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
) -> list[SubsetBasis | UnstatedCut]:
    entries = sheet_entries(study)
    shown = filter_summaries(filters, display_names=display_names(study))
    bases = [
        _filter_basis(each, summary, entries, said, picks)
        for each, summary in zip(filters, shown, strict=True)
    ]
    return [basis for basis in bases if basis is not None]


def _rule_retry(
    cut: UnstatedCut, edges: Mapping[str, TailEdge], noun: str
) -> ModelRetry:
    rules = picked_rule_sentences(edges, cut.variable_name, noun)
    return ModelRetry(
        f"{cut.shown} is a cut no researcher message states. {rules} "
        f"Nothing was written."
    )


def _asked_retry(cut: UnstatedCut, question: OpenQuestion) -> ModelRetry:
    return ModelRetry(
        f"{cut.shown} is a cut no researcher message states and no card "
        f"picked. Nothing was written. {ask_sentence(question)}"
    )


async def _resolved(
    site_id: str,
    dataset_id: str,
    study: EdaStudyDetail,
    held: SubsetBasis | UnstatedCut,
    thread: ThreadRequirements,
) -> SubsetBasis:
    match held:
        case SubsetBasis():
            return held
        case UnstatedCut() as cut:
            return await _asked_or_met(site_id, dataset_id, study, cut, thread)


async def _asked_or_met(
    site_id: str,
    dataset_id: str,
    study: EdaStudyDetail,
    cut: UnstatedCut,
    thread: ThreadRequirements,
) -> SubsetBasis:
    edges = await study_tail_edges(
        site_id,
        dataset_id=dataset_id,
        study=study,
        entity_id=cut.entity_id,
        variable_id=cut.variable_id,
        rules=thread.tail_rules_on(cut.variable_name) if cut.numeric else {},
    )
    met = next(
        (label for label, e in edges.items() if e.binds(cut.at_least, cut.at_most)),
        "",
    )
    if met:
        return SubsetBasis(filter=cut.shown, basis="card", picked=met)
    if edges:
        raise _rule_retry(cut, edges, counted_noun(study, cut.entity_id))
    question = await cut_card(
        site_id,
        dataset_id,
        study,
        entity_id=cut.entity_id,
        variable_id=cut.variable_id,
        variable_name=cut.variable_name,
        numeric=cut.numeric,
    )
    if question.options:
        thread.record_questions([question])
    raise _asked_retry(cut, question)


async def the_subset_basis(
    site_id: str,
    dataset_id: str,
    analysis: EdaAnalysisDetail,
    *,
    said: Sequence[str],
    thread: ThreadRequirements,
) -> list[SubsetBasis]:
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    held = subset_basis(
        analysis.descriptor.subset.descriptor,
        study,
        said=said,
        picks=thread.card_picks,
    )
    return [await _resolved(site_id, dataset_id, study, each, thread) for each in held]
