from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import sqlalchemy.exc
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from pathfinder.platform.config import get_settings
from pathfinder.services.conversations import thread_lock
from pathfinder.services.conversations.thread_lock import hold_thread

pytestmark = pytest.mark.usefixtures("patch_app_db_engine")

DISPATCHES = 15
REQUEST_POOL_TIMEOUT_SECONDS = 1.0
_IDLE_SETTING = text("SELECT current_setting('idle_in_transaction_session_timeout')")


@pytest.fixture
async def one_connection(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(get_settings().database_url, pool_size=1)
    monkeypatch.setattr(thread_lock, "lock_engine", lambda: engine)
    yield engine
    await engine.dispose()


@pytest.fixture
async def request_pool() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        get_settings().database_url,
        pool_size=5,
        max_overflow=10,
        pool_timeout=REQUEST_POOL_TIMEOUT_SECONDS,
    )
    yield engine
    await engine.dispose()


async def test_the_idle_bound_ends_with_the_hold(one_connection: AsyncEngine) -> None:
    async with hold_thread(uuid4()):
        pass

    async with one_connection.connect() as connection:
        after = await connection.scalar(_IDLE_SETTING)

    assert after == "0"


async def _dispatch(request_pool: AsyncEngine, all_locked: asyncio.Barrier) -> None:
    async with hold_thread(uuid4()):
        await all_locked.wait()
        async with request_pool.connect() as connection:
            await connection.execute(text("SELECT 1"))


async def test_a_full_request_pool_of_dispatches_never_waits_on_its_own_locks(
    request_pool: AsyncEngine,
) -> None:
    all_locked = asyncio.Barrier(DISPATCHES)
    await asyncio.gather(
        *(_dispatch(request_pool, all_locked) for _ in range(DISPATCHES)),
    )

    assert (thread_lock.LOCK_POOL_SIZE + thread_lock.LOCK_POOL_OVERFLOW) >= DISPATCHES


async def test_locks_on_the_request_pool_starve_the_dispatches_holding_them(
    request_pool: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(thread_lock, "lock_engine", lambda: request_pool)

    all_locked = asyncio.Barrier(DISPATCHES)
    dispatches = [
        asyncio.create_task(_dispatch(request_pool, all_locked))
        for _ in range(DISPATCHES)
    ]
    finished, _ = await asyncio.wait(
        dispatches,
        timeout=REQUEST_POOL_TIMEOUT_SECONDS / 2,
    )
    outcomes = await asyncio.gather(*dispatches, return_exceptions=True)

    assert finished == set()
    assert sqlalchemy.exc.TimeoutError in {type(outcome) for outcome in outcomes}
