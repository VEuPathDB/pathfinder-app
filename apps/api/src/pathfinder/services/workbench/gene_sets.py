"""The gene-set half of the workbench facade: what the agent and the jobs may
do to a stored gene set."""

from uuid import UUID

from assistant_core.platform.types import JSONObject
from veupathdb_mcp.wdk.enrichment import EnrichmentAnalysisType

from pathfinder.services.gene_sets.enrichment import run_enrichment_for_gene_set
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet


def save_gene_set(gene_set: GeneSet) -> None:
    """Write a gene set into the workbench."""
    get_gene_set_store().save(gene_set)


async def get_gene_set(gene_set_id: str) -> GeneSet | None:
    """The gene set with this id, or None when the workbench holds no such id."""
    return await get_gene_set_store().aget(gene_set_id)


async def list_gene_sets(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
    """The site's gene sets, narrowed to one user when a user is given."""
    store = get_gene_set_store()
    if user_id is None:
        return await store.alist_all(site_id=site_id)
    return await store.alist_for_user(user_id, site_id=site_id)


async def run_gene_set_enrichment(
    gene_set: GeneSet,
    analysis_types: list[EnrichmentAnalysisType],
) -> JSONObject:
    """Run enrichment over a stored gene set and export the results."""
    return await run_enrichment_for_gene_set(gene_set, analysis_types)
