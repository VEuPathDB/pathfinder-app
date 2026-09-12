"""The worker jobs that hold one thread, read from the procrastinate table."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["job_holds_thread"]

# A job is queued until a worker takes it and running until that worker
# reports; procrastinate names those two states, and both write to the thread.
_HOLDS_THREAD = text(
    "SELECT EXISTS (SELECT 1 FROM procrastinate_jobs "
    "WHERE lock = :lock AND status IN ('todo', 'doing'))",
)


async def job_holds_thread(session: AsyncSession, *, conversation_id: UUID) -> bool:
    """Whether a queued or running job locks this thread."""
    result = await session.execute(_HOLDS_THREAD, {"lock": str(conversation_id)})
    return bool(result.scalar_one())
