"""Gene set business logic: create, re-sync, rename, list and delete."""

from uuid import UUID, uuid4

from assistant_core.platform.context import calling_application
from assistant_core.platform.logging import get_logger
from veupathdb.errors import ValidationError
from veupathdb_mcp.wdk import GeneSetWdkContext, resolve_wdk_context

from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet, GeneSetSource

logger = get_logger(__name__)


class EmptyGeneSetError(ValidationError):
    """Raised when a gene set resolves to zero genes."""

    def __init__(self, name: str) -> None:
        super().__init__(
            title="Empty gene set",
            detail=(
                f"'{name}' resolved to 0 genes, so there is nothing to save. "
                "Widen the search (or re-run the strategy) and try again."
            ),
        )


class EmptyResyncError(ValidationError):
    """Raised when a re-sync resolves to zero genes."""

    def __init__(self, name: str) -> None:
        super().__init__(
            title="Empty re-sync",
            detail=(
                f"'{name}' resolved to 0 genes, so the saved set is unchanged. "
                "Check that the strategy still runs on the site, then try again."
            ),
        )


def dedup_ordered(gene_ids: list[str]) -> list[str]:
    """Remove duplicate gene IDs and keep first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for gid in gene_ids:
        if gid not in seen:
            seen.add(gid)
            out.append(gid)
    return out


class GeneSetService:
    """Orchestrates gene-set domain operations over the gene-set store."""

    def __init__(self, store: GeneSetStore) -> None:
        self._store = store

    async def flush(self, gene_set_id: str) -> None:
        """Write a gene set to the database now.

        The default save path is fire-and-forget, so the row may not exist yet.
        """
        entity = self._store.get(gene_set_id)
        if entity is not None:
            await self._store._persist(entity)

    async def get_for_user(self, user_id: UUID, gene_set_id: str) -> GeneSet:
        """Retrieve a gene set owned by this user under this application.

        :raises NotFoundError: If it is missing or held by anyone else.
        """
        gs = await self._store.aget(gene_set_id)
        if gs is None or gs.user_id != user_id:
            msg = f"Gene set not found: {gene_set_id}"
            raise NotFoundError(detail=msg)
        return gs

    async def create(
        self,
        *,
        user_id: UUID,
        name: str,
        site_id: str,
        gene_ids: list[str],
        source: GeneSetSource,
        wdk: GeneSetWdkContext | None = None,
    ) -> GeneSet:
        """Create a gene set, resolving gene IDs from WDK when none are given.

        :raises EmptyGeneSetError: If the gene set resolves to zero genes.
        """
        ctx = wdk or GeneSetWdkContext()
        gene_ids, ctx, step_count = await resolve_wdk_context(site_id, gene_ids, ctx)
        unique_gene_ids = dedup_ordered(gene_ids)
        if not unique_gene_ids:
            raise EmptyGeneSetError(name)

        gs = GeneSet(
            id=str(uuid4()),
            name=name,
            site_id=site_id,
            gene_ids=unique_gene_ids,
            source=source,
            user_id=user_id,
        )
        gs.take_wdk_context(ctx, step_count=step_count)
        self._store.save(gs)
        logger.info(
            "Gene set created",
            gene_set_id=gs.id,
            name=gs.name,
            gene_count=len(gs.gene_ids),
        )
        return gs

    async def resync_strategy(
        self, gene_set_id: str, *, wdk_strategy_id: int, site_id: str
    ) -> GeneSet | None:
        """Replace a gene set snapshot with the current WDK strategy result.

        No step ID is passed, so WDK resolves the current root step. A rebuild
        can give the same strategy ID a new root step, so the set takes the
        whole resolved context and not only its genes. A resolution that reads
        no genes has learnt nothing about the strategy, so it writes nothing.

        :raises EmptyResyncError: If the strategy resolves to zero genes.
        """
        gs = await self._store.aget(gene_set_id)
        if gs is None:
            return None
        gene_ids, ctx, step_count = await resolve_wdk_context(
            site_id,
            [],
            GeneSetWdkContext(
                wdk_strategy_id=wdk_strategy_id, record_type=gs.record_type
            ),
        )
        fresh_gene_ids = dedup_ordered(gene_ids)
        if not fresh_gene_ids:
            raise EmptyResyncError(gs.name)
        gs.gene_ids = fresh_gene_ids
        gs.take_wdk_context(ctx, step_count=step_count)
        self._store.save(gs)
        logger.info(
            "Re-synced strategy gene set",
            gene_set_id=gs.id,
            gene_count=len(gs.gene_ids),
        )
        return gs

    async def rename(self, gene_set: GeneSet, name: str) -> None:
        """Write a new name on the set, durable before the call returns."""
        gene_set.name = name
        self._store.save(gene_set)
        await self.flush(gene_set.id)

    async def record_vdi_publication(
        self, gene_set: GeneSet, vdi_id: str | None
    ) -> None:
        """Point a gene set at the VEuPathDB dataset it was published to.

        The pointer must be durable before the caller reports the publication.
        """
        gene_set.vdi_id = vdi_id
        self._store.save(gene_set)
        await self.flush(gene_set.id)

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        site_id: str | None = None,
    ) -> list[GeneSet]:
        """List gene sets for a user, filtered by site when one is given."""
        return await self._store.alist_for_user(user_id, site_id=site_id)

    def find_by_wdk_strategy(
        self, user_id: UUID, wdk_strategy_id: int
    ) -> GeneSet | None:
        """Find a cached gene set for a WDK strategy."""
        application_id = calling_application()
        for gs in self._store._cache.values():
            if (
                gs.user_id == user_id
                and gs.application_id == application_id
                and gs.wdk_strategy_id == wdk_strategy_id
            ):
                return gs
        return None

    async def delete(self, user_id: UUID, gene_set_id: str) -> None:
        """Delete a gene set. Raise NotFoundError if it is missing or owned by another user."""
        await self.get_for_user(user_id, gene_set_id)
        if not self._store.delete(gene_set_id):
            msg = f"Gene set not found: {gene_set_id}"
            raise NotFoundError(detail=msg)
        logger.info("Gene set deleted", gene_set_id=gene_set_id)
