from __future__ import annotations

import pytest
from assistant_core.platform.db import async_session_factory
from sqlalchemy import text


@pytest.mark.asyncio
async def test_procrastinate_tables_exist(
    db_cleaner: None, patch_app_db_engine: None
) -> None:
    del db_cleaner, patch_app_db_engine
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_name LIKE 'procrastinate_%'
                ORDER BY table_name
                """
            )
        )
        names = [row[0] for row in result.fetchall()]

    assert "procrastinate_jobs" in names
    assert "procrastinate_events" in names
