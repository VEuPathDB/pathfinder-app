from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID

from assistant_core.platform.db import get_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from pathfinder.platform.errors import ThreadBusyError

__all__ = ["HOLD_IDLE_SECONDS", "HOLD_WAIT_SECONDS", "hold_thread", "try_lock_thread"]

HOLD_WAIT_SECONDS = 45.0
HOLD_IDLE_SECONDS = 120.0
_RETRY_SECONDS = 0.1
_IDLE_BOUND = text(
    "SELECT set_config('idle_in_transaction_session_timeout', :bound, true)",
)
_TRY_FOR_THE_TRANSACTION = text(
    "SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))",
)


def _key(conversation_id: UUID) -> str:
    return f"thread:{conversation_id}"


async def _take(
    connection: AsyncConnection,
    conversation_id: UUID,
    wait_seconds: float,
) -> None:
    deadline = time.monotonic() + wait_seconds
    while not await connection.scalar(
        _TRY_FOR_THE_TRANSACTION,
        {"key": _key(conversation_id)},
    ):
        if time.monotonic() >= deadline:
            raise ThreadBusyError
        await asyncio.sleep(_RETRY_SECONDS)


async def _release(
    connection: AsyncConnection,
    end: Callable[[], Awaitable[None]],
) -> None:
    try:
        await asyncio.shield(end())
    except BaseException:
        await connection.invalidate()
        raise


@asynccontextmanager
async def hold_thread(
    conversation_id: UUID,
    *,
    wait_seconds: float = HOLD_WAIT_SECONDS,
    idle_seconds: float = HOLD_IDLE_SECONDS,
) -> AsyncIterator[None]:
    async with get_engine().connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(
                _IDLE_BOUND,
                {"bound": f"{round(idle_seconds * 1000)}ms"},
            )
            await _take(connection, conversation_id, wait_seconds)
            yield
        except BaseException:
            await _release(connection, transaction.rollback)
            raise
        await _release(connection, transaction.commit)


async def try_lock_thread(session: AsyncSession, conversation_id: UUID) -> bool:
    taken = await session.scalar(
        _TRY_FOR_THE_TRANSACTION,
        {"key": _key(conversation_id)},
    )
    return bool(taken)
