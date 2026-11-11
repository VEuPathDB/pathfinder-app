from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from veupathdb.domain import entity_by_id, find_gene_entity
from veupathdb.eda import (
    EdaDistributionResponse,
    EdaEntity,
    EdaNumberRangeFilter,
    EdaStudyDetail,
)

from pathfinder.domain.eda_cut import (
    ClassCount,
    NumericBin,
    TailEdge,
    cut_question,
    tail_edge,
    tail_edges,
)
from pathfinder.domain.strategy.question_options import TailRule
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.services.eda.authoring import preview_subset


@dataclass(frozen=True, slots=True)
class OfferedCut:
    entity_id: str
    variable_id: str
    variable_name: str
    numeric: bool
    classes: Sequence[tuple[str, str]]


def _bins(distribution: EdaDistributionResponse | None) -> list[NumericBin]:
    histogram = [] if distribution is None else distribution.histogram
    return [NumericBin.model_validate(b, from_attributes=True) for b in histogram]


def tail_edges_of(distribution: EdaDistributionResponse | None) -> list[TailEdge]:
    return tail_edges(_bins(distribution))


async def _counted(
    site_id: str,
    *,
    dataset_id: str,
    entity_id: str,
    variable_id: str,
    bins: Sequence[NumericBin],
    edge: TailEdge,
) -> TailEdge:
    first = min(b.bin_start for b in bins)
    last = max(b.bin_end for b in bins)
    low, high = (first, edge.bound) if edge.rule.end == "low" else (edge.bound, last)
    preview = await preview_subset(
        site_id,
        dataset_id=dataset_id,
        entity_id=entity_id,
        filters=[
            EdaNumberRangeFilter(
                entity_id=entity_id, variable_id=variable_id, min=low, max=high
            )
        ],
    )
    return edge.model_copy(update={"count": preview.count})


def class_counts_of(
    distribution: EdaDistributionResponse | None,
    *,
    entity_id: str,
    variable_id: str,
    variable_name: str,
) -> list[ClassCount]:
    histogram = [] if distribution is None else distribution.histogram
    return [
        ClassCount(
            entity_id=entity_id,
            variable_id=variable_id,
            variable_name=variable_name,
            value=b.bin_label,
            count=int(b.value),
        )
        for b in histogram
        if b.value > 0
    ]


def counted_noun(study: EdaStudyDetail, entity_id: str) -> str:
    if find_gene_entity(study, subject="strategy step").entity_id == entity_id:
        return "genes"
    match entity_by_id(study.root_entity, entity_id):
        case EdaEntity(display_name_plural=plural):
            return plural
        case _:
            return entity_id


async def _whole_study(
    site_id: str, dataset_id: str, entity_id: str, variable_id: str
) -> EdaDistributionResponse | None:
    preview = await preview_subset(
        site_id,
        dataset_id=dataset_id,
        entity_id=entity_id,
        filters=[],
        distribution_variable_id=variable_id,
    )
    return preview.distribution


async def study_tail_edges(
    site_id: str,
    *,
    dataset_id: str,
    entity_id: str,
    variable_id: str,
    rules: Mapping[str, TailRule],
) -> dict[str, TailEdge]:
    if not rules:
        return {}
    bins = _bins(await _whole_study(site_id, dataset_id, entity_id, variable_id))
    return {
        label: await _counted(
            site_id,
            dataset_id=dataset_id,
            entity_id=entity_id,
            variable_id=variable_id,
            bins=bins,
            edge=edge,
        )
        for label, rule in rules.items()
        if (edge := tail_edge(bins, rule)) is not None
    }


async def study_cut_question(
    site_id: str,
    *,
    dataset_id: str,
    study: EdaStudyDetail,
    cut: OfferedCut,
) -> OpenQuestion:
    bins = (
        _bins(await _whole_study(site_id, dataset_id, cut.entity_id, cut.variable_id))
        if cut.numeric
        else []
    )
    tails = [
        await _counted(
            site_id,
            dataset_id=dataset_id,
            entity_id=cut.entity_id,
            variable_id=cut.variable_id,
            bins=bins,
            edge=edge,
        )
        for edge in tail_edges(bins)
    ]
    counted = [
        count
        for variable_id, name in cut.classes
        for count in class_counts_of(
            await _whole_study(site_id, dataset_id, cut.entity_id, variable_id),
            entity_id=cut.entity_id,
            variable_id=variable_id,
            variable_name=name,
        )
    ]
    noun = counted_noun(study, cut.entity_id)
    return cut_question(cut.variable_name, noun, tails, counted)
