"""The worker jobs that hold one thread, read from the procrastinate table."""

from __future__ import annotations

from uuid import UUID

from assistant_core.tasks.names import CHAT_TURN_TASK
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["job_holds_thread", "turn_holds_thread", "turns_in_flight"]

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


_TURN_HOLDS_THREAD = text(
    "SELECT EXISTS (SELECT 1 FROM procrastinate_jobs "
    "WHERE task_name = :task AND lock = :lock AND status IN ('todo', 'doing'))",
)


async def turn_holds_thread(session: AsyncSession, *, conversation_id: UUID) -> bool:
    result = await session.execute(
        _TURN_HOLDS_THREAD,
        {"task": CHAT_TURN_TASK, "lock": str(conversation_id)},
    )
    return bool(result.scalar_one())


_TURNS_IN_FLIGHT = text(
    "SELECT count(*) FROM procrastinate_jobs "
    "WHERE task_name = :task AND status IN ('todo', 'doing') "
    "AND args -> 'payload' ->> 'user_id' = :user_id "
    "AND lock IS DISTINCT FROM :lock",
)


async def turns_in_flight(
    session: AsyncSession, *, user_id: UUID, other_than: UUID
) -> int:
    """The user's queued and running chat turns in conversations other than this one."""
    result = await session.execute(
        _TURNS_IN_FLIGHT,
        {"task": CHAT_TURN_TASK, "user_id": str(user_id), "lock": str(other_than)},
    )
    return int(result.scalar_one())
