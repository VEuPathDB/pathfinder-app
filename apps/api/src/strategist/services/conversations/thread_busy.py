from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from assistant_core.persistence.models import BackgroundTask
from assistant_core.persistence.repositories.background_tasks import (
    ACTIVE_TASK_STATES,
)
from assistant_core.tasks.names import CHAT_TURN_TASK
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from strategist.persistence.repositories.checkpoint_rows import parked_approval
from strategist.persistence.repositories.thread_job import job_holds_thread
from strategist.platform.thread_refusals import EditRefusedError
from strategist.services.conversations.thread_lock import try_lock_thread

__all__ = ["ThreadBusy", "claim_settled_thread", "refuse_an_edit_on_a_busy_thread"]


class ThreadBusy(StrEnum):
    LOCKED = "locked"
    TURN = "turn"
    APPROVAL = "approval"
    TASK = "task"


_EDIT_REFUSALS = {
    ThreadBusy.LOCKED: "This chat is changing right now. Try the edit again in a moment.",
    ThreadBusy.TURN: (
        "This chat is still answering. Make this edit once the reply has finished."
    ),
    ThreadBusy.TASK: (
        "This chat is running a background task. "
        "Make this edit once the task has finished."
    ),
}


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
    if await job_holds_thread(
        session,
        conversation_id=conversation_id,
        task=CHAT_TURN_TASK,
    ):
        return ThreadBusy.TURN
    if await _task_is_active(session, conversation_id):
        return ThreadBusy.TASK
    if await parked_approval(session, thread_id=str(conversation_id)) is not None:
        return ThreadBusy.APPROVAL
    return None


async def refuse_an_edit_on_a_busy_thread(
    session: AsyncSession,
    conversation_id: UUID,
) -> None:
    busy = await claim_settled_thread(session, conversation_id)
    if busy is None or busy is ThreadBusy.APPROVAL:
        return
    raise EditRefusedError(_EDIT_REFUSALS[busy])
