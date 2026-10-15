"""The gene-set part of the evidence facade: what the agent and the jobs may
do to a stored gene set."""

from uuid import UUID

from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet


async def store_gene_set(gene_set: GeneSet) -> None:
    """Write a gene set into the gene-set store."""
    await get_gene_set_store().save(gene_set)


async def get_gene_set(gene_set_id: str, *, user_id: UUID | None) -> GeneSet | None:
    """The user's gene set with this id, or None when they own no such set."""
    gene_set = await get_gene_set_store().get(gene_set_id)
    if gene_set is None or user_id is None or gene_set.user_id != user_id:
        return None
    return gene_set


async def list_stored_gene_sets(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
    """The user's gene sets with genes on the site; none when no user is given."""
    if user_id is None:
        return []
    return await get_gene_set_store().list_for_user(user_id, site_id=site_id)
