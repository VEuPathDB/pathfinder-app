"""Whether anything is still going to write to a thread."""

from __future__ import annotations

from uuid import UUID

from assistant_core.conversation.event_stream import latest_event
from assistant_core.tasks.service import has_active_task
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.repositories.thread_job import job_holds_thread
from pathfinder.platform.health import worker_is_alive

__all__ = ["turn_is_in_flight"]

_TURN_TERMINATOR = "done"


class _LoggedChunk(BaseModel):
    """One row of a thread's chunk log, read for its kind alone."""

    model_config = ConfigDict(extra="ignore")

    type: str


async def turn_is_in_flight(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> bool:
    """Whether the thread's tail has anything left to carry.

    An open log does not say a turn runs, and neither does a job row:
    procrastinate releases nothing on its own, so a job outlives the worker
    that held it. A turn is being written when the thread's log is open, a job
    locks the thread, and a worker is beating.
    """
    # The tip is read before the job, which bounds a wrong "nothing is in
    # flight" to the two statements a dispatch takes to log and to defer.
    if (
        await _log_is_open(conversation_id)
        and await job_holds_thread(session, conversation_id=conversation_id)
        and await worker_is_alive(session)
    ):
        return True
    return await has_active_task(session, conversation_id, user_id)


async def _log_is_open(conversation_id: UUID) -> bool:
    """Whether the newest chunk of the thread leaves its turn unterminated."""
    tip = await latest_event(conversation_id)
    if tip is None:
        return False
    return _LoggedChunk.model_validate(tip[1]).type != _TURN_TERMINATOR
