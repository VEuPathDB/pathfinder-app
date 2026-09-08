"""Fixtures the whole integration tier shares."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.community.postgres import PostgresContainer


@pytest.fixture(scope="session", autouse=True)
def settled_database(postgres_container: PostgresContainer | None) -> None:
    """Settle ``DATABASE_URL`` before the first test of the tier.

    A test that reaches the database through a service, and so requests no
    database fixture of its own, otherwise connects to whatever holds the port.
    """
    del postgres_container


@pytest.fixture
async def embedding_index_cleaner(db_engine: AsyncEngine) -> AsyncGenerator[None]:
    """Empty the shared vector store around a test that asserts on it.

    The two tables are a content-addressed cache, so ``db_cleaner`` leaves
    them: a test that re-embeds a whole catalog for every case is a slow test.
    """
    await _truncate_embedding_index(db_engine)
    yield
    await _truncate_embedding_index(db_engine)


async def _truncate_embedding_index(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.exec_driver_sql(
            "TRUNCATE TABLE embedding_index_entries, embedding_vectors",
        )
