"""Gene set business logic: CRUD, set operations, enrichment, and step results."""

from uuid import UUID, uuid4

from assistant_core.platform.context import calling_application
from assistant_core.platform.logging import get_logger
from veupathdb.errors import ValidationError
from veupathdb.wdk import (
    get_strategy_api,
)
from veupathdb_mcp.wdk import (
    GeneSetWdkContext,
    StepResultsService,
    frozen_step_id,
    resolve_wdk_context,
)
from veupathdb_mcp.wdk.enrichment import EnrichmentAnalysisType, EnrichmentResult

from pathfinder.platform.errors import InternalError, NotFoundError
from pathfinder.platform.identity import GENE_SET_STRATEGY_NAME
from pathfinder.services.gene_sets.enrichment import run_enrichment_batch
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

    async def retake_from_source(self, user_id: UUID, gene_set_id: str) -> GeneSet:
        """Replace a set's membership with what its source strategy holds now.

        :raises ValidationError: If the set was not derived from a strategy.
        :raises EmptyResyncError: If the strategy resolves to zero genes.
        """
        gs = await self.get_for_user(user_id, gene_set_id)
        if gs.wdk_strategy_id is None:
            msg = (
                "This gene set was not taken from a strategy, so there is no "
                "source to re-take it from."
            )
            raise ValidationError(detail=msg)
        refreshed = await self.resync_strategy(
            gene_set_id, wdk_strategy_id=gs.wdk_strategy_id, site_id=gs.site_id
        )
        if refreshed is None:
            msg = f"Gene set not found: {gene_set_id}"
            raise NotFoundError(detail=msg)
        return refreshed

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

    async def perform_set_operation(
        self,
        *,
        user_id: UUID,
        set_a_id: str,
        set_b_id: str,
        operation: str,
        name: str,
    ) -> GeneSet:
        """Combine two gene sets with intersect, union, or minus."""
        set_a = await self.get_for_user(user_id, set_a_id)
        set_b = await self.get_for_user(user_id, set_b_id)

        ids_a = set(set_a.gene_ids)
        ids_b = set(set_b.gene_ids)

        match operation:
            case "intersect":
                result_ids = ids_a & ids_b
            case "union":
                result_ids = ids_a | ids_b
            case "minus":
                result_ids = ids_a - ids_b
            case _:
                msg = f"Invalid operation: must be 'intersect', 'union', or 'minus', got '{operation}'"
                raise ValidationError(detail=msg)

        gs = GeneSet(
            id=str(uuid4()),
            name=name,
            site_id=set_a.site_id,
            gene_ids=sorted(result_ids),
            source="derived",
            user_id=user_id,
            parent_set_ids=[set_a.id, set_b.id],
            operation=operation,
        )
        self._store.save(gs)
        logger.info(
            "Gene set derived via set operation",
            gene_set_id=gs.id,
            operation=operation,
            gene_count=len(gs.gene_ids),
        )
        return gs

    async def run_enrichment(
        self,
        user_id: UUID,
        gene_set_id: str,
        enrichment_types: list[EnrichmentAnalysisType],
    ) -> list[EnrichmentResult]:
        """Run enrichment analysis on a gene set."""
        gs = await self.get_for_user(user_id, gene_set_id)
        results, errors = await run_enrichment_batch(gs, enrichment_types)

        if not results and errors:
            msg = "Enrichment analysis failed: " + "; ".join(errors)
            raise InternalError(detail=msg)

        gs.enrichment_results = results
        self._store.save(gs)
        # Enrichment is a slow WDK round trip. The results must be durable
        # before the caller displays them.
        await self.flush(gs.id)
        return results

    async def get_step_results_service(
        self, user_id: UUID, gene_set_id: str
    ) -> StepResultsService:
        """Build a step-results service for a gene set.

        :raises ValidationError: If the gene set has no WDK step.
        """
        gs = await self.get_for_user(user_id, gene_set_id)
        record_type = gs.record_type or "transcript"
        # The set's membership is what it stores. The step it came from can
        # have moved since, and browsing that would show a different set.
        step_id = await frozen_step_id(
            gs.site_id,
            list(gs.gene_ids),
            record_type,
            strategy_name=GENE_SET_STRATEGY_NAME,
        )
        if step_id is None:
            step_id = gs.wdk_step_id
        if not step_id:
            msg = "No genes and no WDK strategy: this gene set has nothing to browse."
            raise ValidationError(detail=msg)
        return StepResultsService(
            get_strategy_api(gs.site_id), step_id=step_id, record_type=record_type
        )
