from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

import sqlalchemy.exc
from assistant_core.platform.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ThreadBusyError

__all__ = [
    "HOLD_IDLE_SECONDS",
    "HOLD_WAIT_SECONDS",
    "LOCK_POOL_OVERFLOW",
    "LOCK_POOL_SIZE",
    "close_lock_engine",
    "hold_thread",
    "lock_engine",
    "try_lock_thread",
]

logger = get_logger(__name__)

HOLD_WAIT_SECONDS = 45.0
HOLD_IDLE_SECONDS = 120.0
LOCK_POOL_SIZE = 2
LOCK_POOL_OVERFLOW = 18
_RETRY_SECONDS = 0.1
_IDLE_BOUND = text(
    "SELECT set_config('idle_in_transaction_session_timeout', :bound, true)",
)
_TRY_FOR_THE_TRANSACTION = text(
    "SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))",
)


class _LockEngine:
    engine: AsyncEngine | None = None


def lock_engine() -> AsyncEngine:
    if _LockEngine.engine is None:
        _LockEngine.engine = create_async_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            pool_size=LOCK_POOL_SIZE,
            max_overflow=LOCK_POOL_OVERFLOW,
            pool_timeout=HOLD_WAIT_SECONDS,
        )
    return _LockEngine.engine


async def close_lock_engine() -> None:
    if _LockEngine.engine is not None:
        await _LockEngine.engine.dispose()
        _LockEngine.engine = None


def _key(conversation_id: UUID) -> str:
    return f"thread:{conversation_id}"


async def _take(
    connection: AsyncConnection,
    conversation_id: UUID,
    deadline: float,
) -> None:
    while not await connection.scalar(
        _TRY_FOR_THE_TRANSACTION,
        {"key": _key(conversation_id)},
    ):
        if asyncio.get_running_loop().time() >= deadline:
            raise ThreadBusyError
        await asyncio.sleep(_RETRY_SECONDS)


async def _release(
    connection: AsyncConnection,
    end: Callable[[], Awaitable[None]],
    conversation_id: UUID,
) -> None:
    try:
        await asyncio.shield(end())
    except asyncio.CancelledError:
        await connection.invalidate()
        raise
    except Exception as exc:
        await connection.invalidate()
        logger.warning(
            "the thread lock did not end cleanly; its connection is discarded",
            conversation_id=str(conversation_id),
            error=type(exc).__name__,
            exc_info=True,
        )


@asynccontextmanager
async def _lock_connection(deadline: float) -> AsyncIterator[AsyncConnection]:
    connection = lock_engine().connect()
    try:
        async with asyncio.timeout_at(deadline):
            await connection.start()
    except (TimeoutError, sqlalchemy.exc.TimeoutError) as exhausted:
        raise ThreadBusyError from exhausted
    try:
        yield connection
    finally:
        await connection.close()


@asynccontextmanager
async def hold_thread(
    conversation_id: UUID,
    *,
    wait_seconds: float = HOLD_WAIT_SECONDS,
    idle_seconds: float = HOLD_IDLE_SECONDS,
) -> AsyncIterator[None]:
    deadline = asyncio.get_running_loop().time() + wait_seconds
    async with _lock_connection(deadline) as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(
                _IDLE_BOUND,
                {"bound": f"{round(idle_seconds * 1000)}ms"},
            )
            await _take(connection, conversation_id, deadline)
            yield
        except BaseException:
            await _release(connection, transaction.rollback, conversation_id)
            raise
        await _release(connection, transaction.commit, conversation_id)


async def try_lock_thread(session: AsyncSession, conversation_id: UUID) -> bool:
    taken = await session.scalar(
        _TRY_FOR_THE_TRANSACTION,
        {"key": _key(conversation_id)},
    )
    return bool(taken)
