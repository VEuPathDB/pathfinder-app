"""The daily sweep deletes the vectors no index names any more."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from veupathdb_mcp.embeddings.db import embedding_session
from veupathdb_mcp.embeddings.record_manager import (
    IndexEntry,
    prune_orphan_vectors,
    sync_index,
)
from veupathdb_mcp.embeddings.tables import EmbeddingVector

from pathfinder.jobs.app import procrastinate_app
from pathfinder.jobs.tasks import ORPHAN_VECTOR_GRACE, ensure_registered


async def _vector_rows() -> int:
    async with embedding_session() as session:
        return (
            await session.scalar(select(func.count()).select_from(EmbeddingVector)) or 0
        )


def test_the_grace_is_a_week() -> None:
    assert timedelta(days=7) == ORPHAN_VECTOR_GRACE


def test_one_name_covers_the_function_and_the_task() -> None:
    """One concept, one name: the task is the function it calls."""
    ensure_registered()

    assert prune_orphan_vectors.__name__ == "prune_orphan_vectors"
    assert "maintenance:prune_orphan_vectors" in procrastinate_app.tasks


def test_the_sweep_runs_once_a_day() -> None:
    ensure_registered()
    registered = procrastinate_app.periodic_registry.periodic_tasks
    assert registered[("maintenance:prune_orphan_vectors", "")].cron == "41 4 * * *"


async def test_the_sweep_drops_an_aged_orphan(
    patch_app_db_engine: None,
    db_cleaner: None,
    embedding_index_cleaner: None,
) -> None:
    del patch_app_db_engine, db_cleaner, embedding_index_cleaner
    await sync_index(
        "catalog:sweepdb",
        [IndexEntry(entry_id="a", text="alpha"), IndexEntry(entry_id="b", text="beta")],
    )
    await sync_index("catalog:sweepdb", [IndexEntry(entry_id="a", text="alpha")])
    async with embedding_session() as session:
        await session.execute(
            update(EmbeddingVector).values(
                created_at=datetime.now(UTC) - timedelta(days=30),
            ),
        )
        await session.commit()

    assert await prune_orphan_vectors(ORPHAN_VECTOR_GRACE) == 1

    assert await _vector_rows() == 1
