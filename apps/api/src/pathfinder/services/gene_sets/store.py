"""Gene set store with write-through DB persistence.

Keeps an in-memory dict for fast synchronous access during AI tool calls,
and persists every mutation to PostgreSQL so gene sets survive API restarts.
"""

from datetime import UTC, datetime
from functools import cache
from typing import cast
from uuid import UUID

# ---------------------------------------------------------------------------
# Row conversion helpers
# ---------------------------------------------------------------------------
from assistant_core.platform.context import calling_application
from assistant_core.platform.db import async_session_factory
from pydantic import TypeAdapter
from sqlalchemy import select
from veupathdb.domain.parameters.values import ParamValue
from veupathdb_mcp.wdk.enrichment import EnrichmentResult

from pathfinder.persistence.models import GeneSetRow
from pathfinder.platform.store import WriteThruStore
from pathfinder.services.gene_sets.types import GeneSet, GeneSetSource

_PARAMS_ADAPTER: TypeAdapter[dict[str, ParamValue]] = TypeAdapter(dict[str, ParamValue])
_ENRICHMENT_ADAPTER: TypeAdapter[list[EnrichmentResult]] = TypeAdapter(
    list[EnrichmentResult]
)


def _row_from_gene_set(gs: GeneSet) -> dict[str, object]:
    serialized_params = (
        _PARAMS_ADAPTER.dump_python(gs.parameters, by_alias=True, mode="json")
        if gs.parameters is not None
        else None
    )
    return {
        "id": gs.id,
        "user_id": gs.user_id,
        "application_id": gs.application_id,
        "site_id": gs.site_id,
        "name": gs.name,
        "gene_ids": gs.gene_ids,
        "source": gs.source,
        "wdk_strategy_id": gs.wdk_strategy_id,
        "wdk_step_id": gs.wdk_step_id,
        "search_name": gs.search_name,
        "record_type": gs.record_type,
        "parameters": serialized_params,
        "parent_set_ids": gs.parent_set_ids,
        "operation": gs.operation,
        "step_count": gs.step_count,
        "enrichment_results": [
            r.model_dump(by_alias=True, mode="json") for r in gs.enrichment_results
        ],
        "vdi_id": gs.vdi_id,
        "created_at": gs.created_at,
    }


def _gene_set_from_row(row: GeneSetRow) -> GeneSet:
    gene_ids = [str(x) for x in row.gene_ids] if row.gene_ids else []
    parent_set_ids = [str(x) for x in row.parent_set_ids] if row.parent_set_ids else []
    parameters = (
        _PARAMS_ADAPTER.validate_python(row.parameters) if row.parameters else None
    )
    valid_sources: set[str] = {"strategy", "paste", "upload", "derived", "saved"}
    source: GeneSetSource = (
        cast("GeneSetSource", row.source) if row.source in valid_sources else "paste"
    )
    return GeneSet(
        id=row.id,
        user_id=row.user_id,
        application_id=row.application_id,
        site_id=row.site_id,
        name=row.name,
        gene_ids=gene_ids,
        source=source,
        created_at=row.created_at or datetime.now(UTC),
        wdk_strategy_id=row.wdk_strategy_id,
        wdk_step_id=row.wdk_step_id,
        search_name=row.search_name,
        record_type=row.record_type,
        parameters=parameters,
        enrichment_results=_ENRICHMENT_ADAPTER.validate_python(
            row.enrichment_results or []
        ),
        parent_set_ids=parent_set_ids,
        operation=row.operation,
        step_count=row.step_count or 1,
        vdi_id=row.vdi_id,
    )


# ---------------------------------------------------------------------------
# DB list helper (domain-specific query, not covered by base class)
# ---------------------------------------------------------------------------


async def _list_from_db(
    user_id: UUID | None = None,
    site_id: str | None = None,
) -> list[GeneSet]:
    stmt = select(GeneSetRow).where(
        GeneSetRow.application_id == calling_application(),
    )
    if user_id:
        stmt = stmt.where(GeneSetRow.user_id == user_id)
    if site_id:
        stmt = stmt.where(GeneSetRow.site_id == site_id)
    stmt = stmt.order_by(GeneSetRow.created_at.desc())

    async with async_session_factory() as session:
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [_gene_set_from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class GeneSetStore(WriteThruStore[GeneSet]):
    """Gene set repository with in-memory cache and DB write-through.

    Inherits save/delete/adelete from WriteThruStore. Every read answers only
    for the calling application, cache included.
    """

    _model = GeneSetRow
    _to_row = staticmethod(_row_from_gene_set)
    _from_row = staticmethod(_gene_set_from_row)

    async def aget(self, entity_id: str) -> GeneSet | None:
        gs = await super().aget(entity_id)
        if gs is None or gs.application_id != calling_application():
            return None
        return gs

    # -- Async listing --------------------------------------------------------

    def _merge_with_cache(
        self,
        db_sets: list[GeneSet],
        *,
        user_id: UUID | None = None,
        site_id: str | None = None,
    ) -> list[GeneSet]:
        """Merge DB rows with in-memory cache (cache wins), filter, and sort."""
        merged: dict[str, GeneSet] = {gs.id: gs for gs in db_sets}
        application_id = calling_application()
        for gid, gs in self._cache.items():
            if gs.application_id != application_id:
                continue
            if user_id is not None and gs.user_id != user_id:
                continue
            if site_id and gs.site_id != site_id:
                continue
            merged[gid] = gs
        result = list(merged.values())
        result.sort(key=lambda gs: gs.created_at, reverse=True)
        return result

    async def alist_all(self, *, site_id: str | None = None) -> list[GeneSet]:
        """List gene sets: merges DB rows with in-memory (fresher) state."""
        db_sets = await _list_from_db(site_id=site_id)
        return self._merge_with_cache(db_sets, site_id=site_id)

    async def alist_for_user(
        self,
        user_id: UUID,
        *,
        site_id: str | None = None,
    ) -> list[GeneSet]:
        db_sets = await _list_from_db(user_id=user_id, site_id=site_id)
        return self._merge_with_cache(db_sets, user_id=user_id, site_id=site_id)


@cache
def get_gene_set_store() -> GeneSetStore:
    """Get the global gene set store singleton."""
    return GeneSetStore()
