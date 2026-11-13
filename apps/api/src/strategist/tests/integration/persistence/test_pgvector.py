"""Verify pgvector extension is installed by Alembic migrations."""

from __future__ import annotations

import pytest
from assistant_core.platform.db import async_session_factory
from sqlalchemy import text


@pytest.mark.asyncio
async def test_pgvector_extension_is_installed(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'"
            )
        )
        row = result.first()
        assert row is not None, "pgvector extension is not installed"
        assert row[0] == "vector"
