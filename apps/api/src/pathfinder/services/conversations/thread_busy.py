from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from assistant_core.persistence.models import BackgroundTask
from assistant_core.persistence.repositories.background_tasks import (
    ACTIVE_TASK_STATES,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.repositories.checkpoint_rows import parked_approval
from pathfinder.persistence.repositories.thread_job import turn_holds_thread
from pathfinder.services.conversations.thread_lock import try_lock_thread

__all__ = ["ThreadBusy", "claim_settled_thread"]


class ThreadBusy(StrEnum):
    LOCKED = "locked"
    TURN = "turn"
    APPROVAL = "approval"
    TASK = "task"


async def _task_is_active(session: AsyncSession, conversation_id: UUID) -> bool:
    found = await session.scalar(
        select(BackgroundTask.id)
        .where(
            BackgroundTask.conversation_id == conversation_id,
            BackgroundTask.status.in_(ACTIVE_TASK_STATES),
        )
        .limit(1),
    )
    return found is not None


async def claim_settled_thread(
    session: AsyncSession,
    conversation_id: UUID,
) -> ThreadBusy | None:
    if not await try_lock_thread(session, conversation_id):
        return ThreadBusy.LOCKED
    if await turn_holds_thread(session, conversation_id=conversation_id):
        return ThreadBusy.TURN
    if await parked_approval(session, thread_id=str(conversation_id)) is not None:
        return ThreadBusy.APPROVAL
    if await _task_is_active(session, conversation_id):
        return ThreadBusy.TASK
    return None
