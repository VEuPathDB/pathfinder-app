"""Which entities a subset filters, measured against the gene entity a step exports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from veupathdb.domain import entity_by_id, find_gene_entity
from veupathdb.eda import EdaAnalysisDetail, EdaFilter, EdaStudyDetail
from veupathdb.errors import ValidationError

from pathfinder.services.eda.authoring import verified_count
from pathfinder.services.eda.catalog import get_study_detail_for_dataset


class NoGeneSubsetError(ValidationError):
    """A subset export whose filters select no gene, so no step holds it."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(title="The subset selects no genes", detail=message)


@dataclass(frozen=True, slots=True)
class GeneSubset:
    """The entities a subset's filters name, and the study's gene entity.

    A step exports genes, so only a filter on the gene entity narrows a step.
    """

    gene_entity_id: str | None
    gene_entity_name: str
    filtered_entity_names: tuple[str, ...]
    num_filters: int
    filters_genes: bool

    def filters_clause(self) -> str:
        """The filters as a count and the entities they name."""
        if not self.num_filters:
            return "no filter"
        noun = "filter" if self.num_filters == 1 else "filters"
        return f"{self.num_filters} {noun} on {', '.join(self.filtered_entity_names)}"

    def gene_entity_clause(self) -> str:
        """The gene entity by its name and its id."""
        return f"{self.gene_entity_name} ({self.gene_entity_id})"


def _entity_name(study: EdaStudyDetail, entity_id: str) -> str:
    entity = entity_by_id(study.root_entity, entity_id)
    return entity_id if entity is None else entity.display_name


def gene_subset(study: EdaStudyDetail, filters: Sequence[EdaFilter]) -> GeneSubset:
    """What ``filters`` select, against the one entity that carries the gene id."""
    gene_id = find_gene_entity(study, subject="strategy step").entity_id
    named = list(dict.fromkeys(entry.entity_id for entry in filters))
    return GeneSubset(
        gene_entity_id=gene_id,
        gene_entity_name="" if gene_id is None else _entity_name(study, gene_id),
        filtered_entity_names=tuple(_entity_name(study, e) for e in named),
        num_filters=len(filters),
        filters_genes=gene_id is not None and gene_id in named,
    )


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _holds_no_gene_subset(subset: GeneSubset, computations: int) -> str:
    """The refusal of a subset export whose filters name no gene entity."""
    held = (
        f"The open analysis holds {subset.filters_clause()} and "
        f"{_counted(computations, 'computation')}, and no filter on the gene "
        f"entity {subset.gene_entity_clause()}. A step exports genes, and a "
        f"subset of another entity selects no genes, so nothing was written."
    )
    gene_filter = f"call set_eda_filters with a filter on {subset.gene_entity_name}."
    if computations:
        return (
            f"{held} The analysis holds a computation: send effect_size_threshold "
            f"and significance_threshold to export the genes that pass them, or "
            f"{gene_filter}"
        )
    return (
        f"{held} Call run_eda_compute to run the comparison and export the genes "
        f"that pass its thresholds, or {gene_filter}"
    )


async def refuse_a_subset_that_selects_no_genes(
    site_id: str,
    *,
    dataset_id: str,
    analysis: EdaAnalysisDetail,
) -> None:
    """A subset export holds a gene-entity filter that selects at least one gene.

    Both the agent's export and the tab's export clear this check. A study with
    no gene entity is left to the export, which names that problem.
    """
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    filters = analysis.descriptor.subset.descriptor
    subset = gene_subset(study, filters)
    if subset.gene_entity_id is None:
        return
    if not subset.filters_genes:
        computations = len(analysis.descriptor.computations)
        raise NoGeneSubsetError(_holds_no_gene_subset(subset, computations))
    counted = await verified_count(
        site_id,
        dataset_id=dataset_id,
        entity_id=subset.gene_entity_id,
        filters=filters,
    )
    if counted.count:
        return
    msg = (
        f"The subset selects 0 of {counted.unfiltered_count:,} genes, so there is "
        "no step to export; nothing was written. For 'up in A versus B' run "
        "run_eda_compute and export the genes that pass its thresholds; to "
        "subset genes directly, widen the filters on "
        f"{subset.gene_entity_name}."
    )
    raise NoGeneSubsetError(msg)
