"""The gene entity a subset filters, and the distinct genes it selects there."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from veupathdb.domain import VEUPATHDB_GENE_ID, entity_by_id, find_gene_entity
from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaFilter,
    EdaStudyDetail,
    differential_expression_computations,
    get_eda_client,
)
from veupathdb.errors import ValidationError

from pathfinder.services.eda.authoring import refuse_an_invalid_subset
from pathfinder.services.eda.catalog import get_study_detail_for_dataset


class NoGeneSubsetError(ValidationError):
    """A subset export that selects no gene, so no step holds it.

    ``detail`` is the researcher's sentence. ``retry`` states the same facts to
    the model, with the tools that change them.
    """

    def __init__(self, *, detail: str, retry: str) -> None:
        self.retry = retry
        super().__init__(title="The subset selects no genes", detail=detail)


@dataclass(frozen=True, slots=True)
class GeneSubset:
    """The entities a subset's filters name, and the study's gene entity.

    A step exports genes, so only a filter on the gene entity narrows a step.
    ``gene_problem`` says why a study has no gene entity.
    """

    gene_entity_id: str | None
    gene_problem: str | None
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


@dataclass(frozen=True, slots=True)
class GeneCount:
    """The distinct gene ids a subset holds, against the whole gene entity's."""

    count: int
    unfiltered_count: int


def _entity_name(study: EdaStudyDetail, entity_id: str) -> str:
    entity = entity_by_id(study.root_entity, entity_id)
    return entity_id if entity is None else entity.display_name


def gene_subset(study: EdaStudyDetail, filters: Sequence[EdaFilter]) -> GeneSubset:
    """What ``filters`` select, against the one entity that carries the gene id."""
    gene = find_gene_entity(study, subject="strategy step")
    gene_id = gene.entity_id
    named = list(dict.fromkeys(entry.entity_id for entry in filters))
    return GeneSubset(
        gene_entity_id=gene_id,
        gene_problem=gene.error,
        gene_entity_name="" if gene_id is None else _entity_name(study, gene_id),
        filtered_entity_names=tuple(_entity_name(study, e) for e in named),
        num_filters=len(filters),
        filters_genes=gene_id is not None and gene_id in named,
    )


async def gene_count(
    site_id: str,
    *,
    study: EdaStudyDetail,
    entity_id: str,
    filters: Sequence[EdaFilter],
) -> GeneCount:
    """The distinct gene ids of ``entity_id`` under ``filters``, and under none.

    The caller validates ``filters`` against ``study``. A row of the gene
    entity can be one gene in one sample, so its row count is not a gene count.
    """
    client = get_eda_client(site_id)
    try:
        async with asyncio.TaskGroup() as group:
            filtered, whole = (
                group.create_task(
                    client.distribution(
                        study_id=study.id,
                        entity_id=entity_id,
                        variable_id=VEUPATHDB_GENE_ID,
                        filters=applied,
                    )
                )
                for applied in (filters, [])
            )
    except ExceptionGroup as failed:
        # The service's own refusal is what the caller words for the researcher.
        raise failed.exceptions[0] from None
    return GeneCount(
        count=filtered.result().statistics.num_distinct_values,
        unfiltered_count=whole.result().statistics.num_distinct_values,
    )


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _no_gene_entity(problem: str | None) -> NoGeneSubsetError:
    return NoGeneSubsetError(
        detail=(
            "This study has no single gene variable, so it cannot export genes "
            "as a step. Nothing was written."
        ),
        retry=(
            f"{problem} Nothing was written. Report the counts and the "
            f"distributions instead."
        ),
    )


def _no_gene_filter(subset: GeneSubset, comparisons: int) -> NoGeneSubsetError:
    """The refusal of a subset export whose filters name no gene entity."""
    gene = subset.gene_entity_name
    held = (
        f"The analysis holds {subset.filters_clause()} and "
        f"{_counted(comparisons, 'comparison')}, and no filter on {gene}. A "
        f"step holds genes, and a subset of another entity selects no genes, so "
        f"nothing was written."
    )
    named = f"The gene entity is {subset.gene_entity_clause()}."
    if comparisons:
        return NoGeneSubsetError(
            detail=(
                f"{held} Export the genes that pass a volcano cut, or add a "
                f"filter on {gene}."
            ),
            retry=(
                f"{held} {named} Send effect_size_threshold and "
                f"significance_threshold to export the genes that pass them, or "
                f"call set_eda_filters with a filter on {gene}."
            ),
        )
    return NoGeneSubsetError(
        detail=(
            f"{held} Run a differential expression comparison and export the "
            f"genes that pass its cut, or add a filter on {gene}."
        ),
        retry=(
            f"{held} {named} Call run_eda_compute to run the comparison and "
            f"export the genes that pass its thresholds, or call set_eda_filters "
            f"with a filter on {gene}."
        ),
    )


def _no_gene_selected(subset: GeneSubset, counted: GeneCount) -> NoGeneSubsetError:
    gene = subset.gene_entity_name
    held = (
        f"The subset selects 0 of the {counted.unfiltered_count:,} genes on "
        f"{gene}, so there is no step to export and nothing was written."
    )
    return NoGeneSubsetError(
        detail=(
            f"{held} Widen the filters on {gene}, or run a differential "
            f"expression comparison and export the genes that pass its cut."
        ),
        retry=(
            f"{held} To subset genes, widen the filters on {gene} with "
            f"set_eda_filters. For 'up in A versus B', call run_eda_compute and "
            f"export the genes that pass its thresholds."
        ),
    )


async def refuse_a_subset_that_selects_no_genes(
    site_id: str,
    *,
    dataset_id: str,
    analysis: EdaAnalysisDetail,
) -> None:
    """A subset export holds a gene-entity filter that selects at least one gene.

    Both the agent's export and the tab's export clear this check.
    """
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    filters = analysis.descriptor.subset.descriptor
    subset = gene_subset(study, filters)
    if subset.gene_entity_id is None:
        raise _no_gene_entity(subset.gene_problem)
    if not subset.filters_genes:
        comparisons = differential_expression_computations(analysis.descriptor)
        raise _no_gene_filter(subset, len(comparisons))
    refuse_an_invalid_subset(study, filters)
    counted = await gene_count(
        site_id, study=study, entity_id=subset.gene_entity_id, filters=filters
    )
    if not counted.count:
        raise _no_gene_selected(subset, counted)
