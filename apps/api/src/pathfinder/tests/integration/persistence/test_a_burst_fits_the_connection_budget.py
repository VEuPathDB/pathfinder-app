from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.memory.lifespan import lifespan_memory_store
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from pathfinder.platform.config import get_settings
from pathfinder.platform.connection_budget import CONNECTION_BUDGET
from pathfinder.services.conversations.thread_lock import hold_thread

pytestmark = pytest.mark.usefixtures("patch_app_db_engine")

DISPATCHES = 15
BURST_DEADLINE_SECONDS = 60.0
HOLD_SECONDS = 1.0
_OPEN = text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")


@dataclass
class _Peak:
    connections: int = 0


def _request_pool() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
    )


@pytest.fixture
async def api_pool() -> AsyncIterator[AsyncEngine]:
    engine = _request_pool()
    yield engine
    await engine.dispose()


@pytest.fixture
async def worker_pool() -> AsyncIterator[AsyncEngine]:
    engine = _request_pool()
    yield engine
    await engine.dispose()


async def _dispatch(api_pool: AsyncEngine) -> None:
    async with hold_thread(uuid4()), api_pool.connect() as connection:
        await connection.execute(text("SELECT 1"))
        await asyncio.sleep(HOLD_SECONDS)


async def _audit_job(worker_pool: AsyncEngine) -> None:
    async with worker_pool.connect() as lease, worker_pool.connect() as work:
        await lease.execute(text("SELECT pg_try_advisory_lock(42)"))
        await work.execute(text("SELECT 1"))
        await asyncio.sleep(HOLD_SECONDS)
        await lease.execute(text("SELECT pg_advisory_unlock(42)"))


async def _durable_job(worker_pool: AsyncEngine) -> None:
    url = get_settings().database_url
    async with (
        lifespan_memory_store(url),
        lifespan_checkpointer(url),
        worker_pool.connect() as work,
    ):
        await work.execute(text("SELECT 1"))
        await asyncio.sleep(HOLD_SECONDS)


async def _watch(engine: AsyncEngine, peak: _Peak, done: asyncio.Event) -> None:
    async with engine.connect() as connection:
        while not done.is_set():
            peak.connections = max(
                peak.connections, int(await connection.scalar(_OPEN))
            )
            await asyncio.sleep(0.05)


async def test_dispatches_an_audit_and_a_durable_job_fit_together(
    api_pool: AsyncEngine,
    worker_pool: AsyncEngine,
) -> None:
    peak = _Peak()
    done = asyncio.Event()
    watching = create_async_engine(
        get_settings().database_url,
        pool_size=1,
        isolation_level="AUTOCOMMIT",
    )
    watcher = asyncio.create_task(_watch(watching, peak, done))
    try:
        outcomes = await asyncio.wait_for(
            asyncio.gather(
                *(_dispatch(api_pool) for _ in range(DISPATCHES)),
                _audit_job(worker_pool),
                _durable_job(worker_pool),
                return_exceptions=True,
            ),
            timeout=BURST_DEADLINE_SECONDS,
        )
    finally:
        done.set()
        await watcher
        await watching.dispose()

    assert outcomes == [None] * (DISPATCHES + 2)
    assert 0 < peak.connections <= CONNECTION_BUDGET
