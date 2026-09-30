"""Experiment repository: the rows of ``experiments``."""

from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ExperimentRow


class ExperimentRepository:
    """Writes experiment rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def put(self, row: ExperimentRow) -> None:
        """Insert the row, or replace every column of the row with its id."""
        await self.session.merge(row)
        await self.session.flush()
