"""The lock that serializes the strategy writes of one thread."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import UUID

from assistant_core.platform.db import DBSessionFactory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.services.strategies.context import StrategyMutationContext


@asynccontextmanager
async def strategy_write_lock(
    conversation_id: UUID,
    session_factory: DBSessionFactory,
) -> AsyncIterator[AsyncSession]:
    """Own the thread's strategy for a whole read-modify-write.

    A mutation reads the stored AST, edits it in memory and writes the whole
    tree back. Two mutations that read the same AST both write it, and the
    later write drops the earlier edit, so the read and the write belong in
    one lock.
    """
    async with session_factory() as session:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"strategy:{conversation_id}"},
        )
        yield session
        await session.commit()


@asynccontextmanager
async def _joined(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """The caller's locked transaction; the caller commits it."""
    yield session


def writes_a_thread(deps: StrategyMutationContext) -> bool:
    """Whether the context stores its writes on a thread."""
    return deps.conversation_id is not None and (
        deps.locked_session is not None or deps.db_session_factory is not None
    )


def strategy_write_scope(
    deps: StrategyMutationContext,
) -> AbstractAsyncContextManager[AsyncSession] | None:
    """The transaction that owns the thread's strategy for one write.

    A caller that already holds the lock passes its session on the context, so
    every write of the edit joins that transaction. A second session against
    the same row would wait on a lock the caller never releases.

    ``None`` when the context names no thread to write to.
    """
    if deps.conversation_id is None:
        return None
    if deps.locked_session is not None:
        return _joined(deps.locked_session)
    if deps.db_session_factory is None:
        return None
    return strategy_write_lock(deps.conversation_id, deps.db_session_factory)
