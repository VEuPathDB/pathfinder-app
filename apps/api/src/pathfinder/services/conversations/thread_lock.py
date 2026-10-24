from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from assistant_core.platform.db import get_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["hold_thread", "try_lock_thread"]

_HOLD = text("SELECT pg_advisory_lock(hashtextextended(:key, 0))")
_RELEASE = text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))")
_TRY_FOR_THE_TRANSACTION = text(
    "SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))",
)


def _key(conversation_id: UUID) -> str:
    return f"thread:{conversation_id}"


@asynccontextmanager
async def hold_thread(conversation_id: UUID) -> AsyncIterator[None]:
    async with get_engine().connect() as connection:
        await connection.execute(_HOLD, {"key": _key(conversation_id)})
        await connection.commit()
        try:
            yield
        finally:
            await connection.execute(_RELEASE, {"key": _key(conversation_id)})
            await connection.commit()


async def try_lock_thread(session: AsyncSession, conversation_id: UUID) -> bool:
    taken = await session.scalar(
        _TRY_FOR_THE_TRANSACTION,
        {"key": _key(conversation_id)},
    )
    return bool(taken)
