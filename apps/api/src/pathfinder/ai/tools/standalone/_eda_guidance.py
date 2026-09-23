"""What an EDA analysis result means, and what it does not mean."""

from __future__ import annotations

from pathfinder.services.eda.authoring import SubsetCount, SubsetPreview
from pathfinder.services.eda.gene_subset import GeneSubset

SHEET_GUIDANCE = (
    "The sheet is pinned under 'Open EDA filter sheet' in your instructions. "
    "Send the whole filters array back, then call preview_eda_subset."
)

APPLIED_GUIDANCE = (
    "Call preview_eda_subset before you state any count. The filters can "
    "select nothing, and the service reports that as a plain zero."
)


def opened_guidance(*, gene_problem: str | None, can_export: bool) -> str:
    """What to do next, and what this study cannot do."""
    lines = [
        (
            "Call set_eda_filters with no filters to read the filter sheet, then "
            "again with the whole filter array."
        ),
    ]
    if gene_problem is not None:
        lines.append(
            f"{gene_problem} This analysis cannot export rows into a strategy "
            f"step; report the counts and the distributions instead."
        )
    elif not can_export:
        lines.append(
            "This account cannot export this study's rows, so the analysis "
            "cannot export rows into a strategy step."
        )
    return " ".join(lines)


def entity_count_clause(preview: SubsetPreview) -> str:
    """One clause per entity a preview carries: kept of total, then the name."""
    return (
        f"{preview.count:,} of {preview.unfiltered_count:,} "
        f"{preview.entity_display_name}"
    )


def preview_guidance(
    *,
    preview_count: int,
    unfiltered_count: int,
    entity_display_name: str,
    has_filters: bool,
    is_multi_valued: bool,
    num_missing_cases: int,
) -> str:
    """What this count means, and what it does not mean."""
    lines: list[str] = []
    if preview_count == 0:
        lines.append(
            f"This subset selects no records on {entity_display_name}. Name the "
            f"filter that emptied it and offer one way to widen it."
        )
    elif preview_count == unfiltered_count and has_filters:
        lines.append(
            "The subset is the whole entity, so these filters narrow nothing "
            "here. They may still narrow another entity."
        )
    if is_multi_valued:
        lines.append(
            "This variable holds several values per record, so the histogram's "
            "values sum above the record count. State which denominator any "
            "percentage uses."
        )
    if num_missing_cases:
        lines.append(
            f"{num_missing_cases} records on this entity have no value for that "
            f"variable."
        )
    return " ".join(lines)


def no_gene_subset_sentence(preview: SubsetPreview, *, subset: GeneSubset) -> str:
    """The count of another entity, under a subset that names no gene filter."""
    return (
        f"{preview.count:,} of {preview.unfiltered_count:,} "
        f"{preview.entity_display_name_plural} "
        f"selected; this subset does not filter genes, because it holds "
        f"{subset.filters_clause()}. A step exports genes, so run run_eda_compute "
        f"or filter the gene entity {subset.gene_entity_clause()} before "
        f"create_eda_step."
    )


def gene_count_sentence(genes: SubsetCount) -> str:
    """The gene count beside a count of another entity."""
    return (
        f"Genes this subset selects: {genes.count:,} of {genes.unfiltered_count:,}. "
        "A step exports genes, so that is the count a step would hold."
    )
