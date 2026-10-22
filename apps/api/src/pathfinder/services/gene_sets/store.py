"""The gene set store: every call reads or writes the ``gene_sets`` table.

The api and the worker both write gene sets, so no process keeps a copy.
"""

from datetime import UTC, datetime
from functools import cache
from typing import cast
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from pydantic import TypeAdapter
from veupathdb.domain.parameters import ParamValue

from pathfinder.domain.gene_homes import GeneHome
from pathfinder.persistence.models import GeneSetRow
from pathfinder.persistence.repositories.gene_set import GeneSetRepository
from pathfinder.services.gene_sets.homes import site_kind
from pathfinder.services.gene_sets.types import (
    GeneSet,
    GeneSetSource,
    OutOfDate,
)

_PARAMS_ADAPTER: TypeAdapter[dict[str, ParamValue]] = TypeAdapter(dict[str, ParamValue])
_HOMES_ADAPTER: TypeAdapter[dict[str, GeneHome]] = TypeAdapter(dict[str, GeneHome])
_OUT_OF_DATE_ADAPTER: TypeAdapter[OutOfDate | None] = TypeAdapter(OutOfDate | None)


def _row_from_gene_set(gs: GeneSet) -> GeneSetRow:
    serialized_params = (
        _PARAMS_ADAPTER.dump_python(gs.parameters, by_alias=True, mode="json")
        if gs.parameters is not None
        else None
    )
    return GeneSetRow(
        id=gs.id,
        user_id=gs.user_id,
        application_id=gs.application_id,
        site_id=gs.site_id,
        name=gs.name,
        gene_ids=list(gs.gene_ids),
        source=gs.source,
        wdk_strategy_id=gs.wdk_strategy_id,
        wdk_step_id=gs.wdk_step_id,
        search_name=gs.search_name,
        record_type=gs.record_type,
        parameters=serialized_params,
        step_count=gs.step_count,
        vdi_id=gs.vdi_id,
        conversation_id=gs.conversation_id,
        answer_revision=gs.answer_revision,
        homes=_HOMES_ADAPTER.dump_python(gs.homes, by_alias=True, mode="json"),
        out_of_date=_OUT_OF_DATE_ADAPTER.dump_python(
            gs.out_of_date, by_alias=True, mode="json"
        ),
        created_at=gs.created_at,
    )


def _gene_set_from_row(row: GeneSetRow) -> GeneSet:
    gene_ids = [str(x) for x in row.gene_ids] if row.gene_ids else []
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
        step_count=row.step_count or 1,
        vdi_id=row.vdi_id,
        conversation_id=row.conversation_id,
        answer_revision=row.answer_revision,
        homes=_HOMES_ADAPTER.validate_python(row.homes or {}),
        out_of_date=_OUT_OF_DATE_ADAPTER.validate_python(row.out_of_date),
    )


class GeneSetStore:
    """Gene sets of the calling application, read from and written to the database."""

    async def save(self, gene_set: GeneSet) -> None:
        """Write every field of the set, durable before the call returns."""
        async with async_session_factory() as session:
            await GeneSetRepository(session).put(_row_from_gene_set(gene_set))
            await session.commit()

    async def get(self, gene_set_id: str) -> GeneSet | None:
        async with async_session_factory() as session:
            row = await GeneSetRepository(session).get_by_id(gene_set_id)
            return None if row is None else _gene_set_from_row(row)

    async def rename(self, gene_set_id: str, name: str) -> None:
        async with async_session_factory() as session:
            await GeneSetRepository(session).set_name(gene_set_id, name)
            await session.commit()

    async def set_vdi_id(self, gene_set_id: str, vdi_id: str | None) -> None:
        async with async_session_factory() as session:
            await GeneSetRepository(session).set_vdi_id(gene_set_id, vdi_id)
            await session.commit()

    async def set_out_of_date(
        self, gene_set_id: str, out_of_date: OutOfDate | None
    ) -> None:
        async with async_session_factory() as session:
            await GeneSetRepository(session).set_out_of_date(
                gene_set_id,
                _OUT_OF_DATE_ADAPTER.dump_python(
                    out_of_date, by_alias=True, mode="json"
                ),
            )
            await session.commit()

    async def delete(self, gene_set_id: str) -> bool:
        """Delete the set. Returns whether the set was there to delete."""
        async with async_session_factory() as session:
            removed = await GeneSetRepository(session).delete_by_id(gene_set_id)
            await session.commit()
            return removed

    async def list_for_user(
        self, user_id: UUID, *, site_id: str | None = None
    ) -> list[GeneSet]:
        """The user's sets, newest first; on a site, the sets with genes there."""
        async with async_session_factory() as session:
            rows = await GeneSetRepository(session).list_newest_first(user_id=user_id)
            sets = [_gene_set_from_row(r) for r in rows]
        if site_id is None:
            return sets
        kind = site_kind(site_id)
        return [gs for gs in sets if gs.genes_on(site_id, kind)]

    async def find_strategy_import(
        self, user_id: UUID, wdk_strategy_id: int
    ) -> GeneSet | None:
        """The set a strategy import made for this WDK strategy, if one exists."""
        async with async_session_factory() as session:
            row = await GeneSetRepository(session).find_strategy_import(
                user_id, wdk_strategy_id
            )
            return None if row is None else _gene_set_from_row(row)


@cache
def get_gene_set_store() -> GeneSetStore:
    """Get the global gene set store singleton."""
    return GeneSetStore()
