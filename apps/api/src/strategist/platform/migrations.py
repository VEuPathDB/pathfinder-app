"""Brings the database schema to the latest revision at startup."""

from pathlib import Path

import assistant_core.migrate
import veupathdb_mcp.migrate
from alembic import command
from alembic.config import Config
from assistant_core.platform.db import get_engine
from sqlalchemy.engine import Connection

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"

# The graph checkpointer and the memory store build these when they open.
LANGGRAPH_TABLES = frozenset(
    {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
        "store",
        "store_vectors",
        "store_migrations",
        "vector_migrations",
    }
)

# Procrastinate publishes no list of its tables. Its schema names every one of
# them with this prefix.
PROCRASTINATE_PREFIX = "procrastinate_"

# Tables another distribution builds and migrates in this database: the runtime
# and the tool server each name their own, and each stamps a version table.
FOREIGN_TABLES = frozenset(
    {
        *assistant_core.migrate.OWNED_TABLES,
        assistant_core.migrate.VERSION_TABLE,
        *veupathdb_mcp.migrate.OWNED_TABLES,
        veupathdb_mcp.migrate.VERSION_TABLE,
        *LANGGRAPH_TABLES,
    }
)


def include_object(
    _object: object,
    name: str | None,
    type_: str,
    _reflected: object,
    _compare_to: object,
) -> bool:
    """Drop every table another distribution owns from autogenerate.

    This chain shares its metadata base with the runtime, and four
    distributions build tables here that no model in this application maps.
    """
    if type_ != "table" or name is None:
        return True
    return name not in FOREIGN_TABLES and not name.startswith(PROCRASTINATE_PREFIX)


def upgrade_all(connection: Connection) -> None:
    """Run the three chains synchronously on a connection.

    The application's chain runs first: the tables the other two build name
    its tables in foreign keys. Each distribution records its position in a
    version table of its own.
    """
    alembic_cfg = Config(str(ALEMBIC_INI))
    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")
    veupathdb_mcp.migrate.upgrade_head(connection)
    assistant_core.migrate.upgrade_head(connection)


async def init_db() -> None:
    """Initialize the database by migrating to the latest revision."""
    async with get_engine().begin() as conn:
        await conn.run_sync(upgrade_all)
