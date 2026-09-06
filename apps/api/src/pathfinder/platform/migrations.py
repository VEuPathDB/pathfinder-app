"""Brings the database schema to the latest revision at startup."""

from alembic import command
from alembic.config import Config
from assistant_core.platform.db import get_engine
from sqlalchemy.engine import Connection
from veupathdb_mcp import migrate


def _run_alembic_upgrade(connection: Connection) -> None:
    """Run both chains synchronously on a connection.

    The application owns its tables; the embedding index is a separate
    distribution and carries its own history and its own version table.
    """
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")
    migrate.upgrade_head(connection)


async def init_db() -> None:
    """Initialize the database by migrating to the latest revision."""
    async with get_engine().begin() as conn:
        await conn.run_sync(_run_alembic_upgrade)
