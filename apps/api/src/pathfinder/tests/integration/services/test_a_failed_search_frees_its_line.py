from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from veupathdb.wdk import search_gate, use_search_gate
from veupathdb_mcp.search_line import (
    ExpensiveSearchLine,
    install_search_line,
    search_line_key,
)

from pathfinder.platform.config import get_settings
from pathfinder.services.search_waits import runs_on_the_deployment_line

SITE = "plasmodb"
REFUSED = "the search failed inside its line"
_LINE_LOCKS = text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")
_TAKE = text("SELECT pg_try_advisory_lock(hashtextextended(:line, 0))")
_RELEASE = text("SELECT pg_advisory_unlock(hashtextextended(:line, 0))")

pytestmark = pytest.mark.usefixtures("patch_app_db_engine")


@pytest.fixture
async def deployment_line() -> AsyncIterator[ExpensiveSearchLine]:
    settings = get_settings()
    installed = search_gate()
    engine = install_search_line(
        settings.database_url,
        runs_on_the_deployment_line,
        pool_size=settings.search_line_pool_size,
        max_overflow=settings.search_line_max_overflow,
        pool_timeout=settings.search_line_pool_timeout_seconds,
    )
    yield ExpensiveSearchLine(engine)
    use_search_gate(installed)
    await engine.dispose()


async def _held_and_free() -> tuple[int, bool]:
    other = create_async_engine(get_settings().database_url, pool_size=1)
    try:
        async with other.connect() as connection:
            held = int(await connection.scalar(_LINE_LOCKS))
            line = {"line": search_line_key(SITE)}
            taken = bool(await connection.scalar(_TAKE, line))
            if taken:
                await connection.execute(_RELEASE, line)
    finally:
        await other.dispose()
    return held, taken


async def _fail_inside(line: ExpensiveSearchLine) -> None:
    async with line.hold(SITE):
        raise RuntimeError(REFUSED)


async def test_a_search_that_raises_inside_its_line_frees_it(
    deployment_line: ExpensiveSearchLine,
) -> None:
    with pytest.raises(RuntimeError, match=REFUSED):
        await _fail_inside(deployment_line)

    assert await _held_and_free() == (0, True)


async def test_a_search_cancelled_inside_its_line_frees_it(
    deployment_line: ExpensiveSearchLine,
) -> None:
    inside = asyncio.Event()

    async def _search() -> None:
        async with deployment_line.hold(SITE):
            inside.set()
            await asyncio.Event().wait()

    search = asyncio.create_task(_search())
    await inside.wait()
    search.cancel()
    with pytest.raises(asyncio.CancelledError):
        await search

    assert await _held_and_free() == (0, True)
