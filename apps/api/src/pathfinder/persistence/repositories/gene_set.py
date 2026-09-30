"""Gene set repository: the calling application's rows of ``gene_sets``."""

from uuid import UUID

from assistant_core.platform.context import calling_application
from sqlalchemy import Select, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import GeneSetRow


def _owned() -> Select[tuple[GeneSetRow]]:
    return select(GeneSetRow).where(GeneSetRow.application_id == calling_application())


class GeneSetRepository:
    """Reads and writes gene set rows. Every read and every edit answers only
    for the calling application."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def put(self, row: GeneSetRow) -> None:
        """Insert the row, or replace every column of the row with its id."""
        await self.session.merge(row)
        await self.session.flush()

    async def get_by_id(self, gene_set_id: str) -> GeneSetRow | None:
        result = await self.session.execute(
            _owned().where(GeneSetRow.id == gene_set_id)
        )
        return result.scalar_one_or_none()

    async def list_newest_first(
        self, *, user_id: UUID | None, site_id: str | None
    ) -> list[GeneSetRow]:
        """The rows of one user and one site, when either is given."""
        stmt = _owned()
        if user_id is not None:
            stmt = stmt.where(GeneSetRow.user_id == user_id)
        if site_id:
            stmt = stmt.where(GeneSetRow.site_id == site_id)
        result = await self.session.execute(stmt.order_by(GeneSetRow.created_at.desc()))
        return list(result.scalars().all())

    async def find_strategy_import(
        self, user_id: UUID, wdk_strategy_id: int
    ) -> GeneSetRow | None:
        """The oldest set a strategy import made for this WDK strategy.

        An import takes the strategy's result in no thread, so a set saved in
        a thread, or with another source, never matches.
        """
        stmt = (
            _owned()
            .where(
                GeneSetRow.user_id == user_id,
                GeneSetRow.wdk_strategy_id == wdk_strategy_id,
                GeneSetRow.source == "strategy",
                GeneSetRow.conversation_id.is_(None),
            )
            .order_by(GeneSetRow.created_at)
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def set_name(self, gene_set_id: str, name: str) -> None:
        """Write the name alone, so a concurrent write of the genes stands."""
        await self.session.execute(
            update(GeneSetRow)
            .where(
                GeneSetRow.id == gene_set_id,
                GeneSetRow.application_id == calling_application(),
            )
            .values(name=name)
        )

    async def set_vdi_id(self, gene_set_id: str, vdi_id: str | None) -> None:
        """Write the dataset pointer alone, so a concurrent write of the genes stands."""
        await self.session.execute(
            update(GeneSetRow)
            .where(
                GeneSetRow.id == gene_set_id,
                GeneSetRow.application_id == calling_application(),
            )
            .values(vdi_id=vdi_id)
        )

    async def delete_by_id(self, gene_set_id: str) -> bool:
        """Delete the row. Returns whether a row was there to delete."""
        result = await self.session.execute(
            delete(GeneSetRow)
            .where(
                GeneSetRow.id == gene_set_id,
                GeneSetRow.application_id == calling_application(),
            )
            .returning(GeneSetRow.id)
        )
        return result.scalar_one_or_none() is not None
