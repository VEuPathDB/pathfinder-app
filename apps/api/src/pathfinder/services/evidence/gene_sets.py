"""The gene-set part of the evidence facade: what the agent and the jobs may
do to a stored gene set."""

from uuid import UUID

from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet


def store_gene_set(gene_set: GeneSet) -> None:
    """Write a gene set into the gene-set store."""
    get_gene_set_store().save(gene_set)


async def get_gene_set(gene_set_id: str) -> GeneSet | None:
    """The gene set with this id, or None when the store holds no such id."""
    return await get_gene_set_store().aget(gene_set_id)


async def list_stored_gene_sets(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
    """The site's gene sets, narrowed to one user when a user is given."""
    store = get_gene_set_store()
    if user_id is None:
        return await store.alist_all(site_id=site_id)
    return await store.alist_for_user(user_id, site_id=site_id)
