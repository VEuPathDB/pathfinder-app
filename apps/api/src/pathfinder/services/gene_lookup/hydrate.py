"""Fill the gaps in sparse gene results with WDK metadata."""

from assistant_core.platform.logging import get_logger

from pathfinder.platform.errors import AppError
from pathfinder.platform.text import strip_html_tags

from .organism import normalize_organism
from .result import GeneResult
from .wdk import resolve_gene_ids

logger = get_logger(__name__)


def _merge_meta(merged: GeneResult, meta: GeneResult) -> GeneResult:
    """Fill empty fields in *merged* from *meta*, applying transforms."""
    return GeneResult(
        gene_id=merged.gene_id,
        display_name=(
            merged.display_name
            or merged.gene_name
            or merged.product
            or meta.product
            or merged.gene_id
        ),
        organism=merged.organism or normalize_organism(meta.organism),
        product=merged.product or strip_html_tags(meta.product),
        gene_name=merged.gene_name or strip_html_tags(meta.gene_name),
        gene_type=merged.gene_type or meta.gene_type,
        location=merged.location or meta.location,
        previous_ids=merged.previous_ids,
        matched_fields=merged.matched_fields,
    )


async def hydrate_sparse_gene_results(
    site_id: str,
    results: list[GeneResult],
    limit: int,
) -> list[GeneResult]:
    """Fill an absent organism or product from the WDK standard reporter.

    Site-search returns ``summaryFieldData`` only for the fields the query
    matched, so a gene matched in literature carries no organism and no
    product.
    """
    ids_to_hydrate: list[str] = [
        r.gene_id for r in results if r.gene_id and (not r.organism or not r.product)
    ]
    if not ids_to_hydrate:
        return results

    try:
        resolved = await resolve_gene_ids(
            site_id,
            ids_to_hydrate[:50],
            record_type="transcript",
        )
    except AppError as exc:
        logger.debug(
            "Gene metadata hydration via WDK skipped",
            site_id=site_id,
            count=len(ids_to_hydrate),
            error=str(exc),
        )
        return results

    if resolved.error:
        return results

    if not resolved.records:
        return results

    by_id: dict[str, GeneResult] = {}
    for rec in resolved.records:
        if rec.gene_id:
            by_id[rec.gene_id.strip()] = rec

    hydrated: list[GeneResult] = []
    for r in results:
        meta = by_id.get(r.gene_id) if r.gene_id else None
        if not meta:
            hydrated.append(r)
            continue
        hydrated.append(_merge_meta(r, meta))

    return hydrated[:limit]
