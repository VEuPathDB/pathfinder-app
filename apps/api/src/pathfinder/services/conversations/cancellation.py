"""Turn-cancellation service for conversations.

Stop writes a request row that the worker running the turn polls. When that
worker has been silent for longer than ``worker_dead_heartbeat_seconds``, Stop
also ends the turn here and now. A worker that died more recently than that
window still owns its turn, so Stop leaves the request for the maintenance
sweep to act on.
"""

import asyncio
import time
from collections.abc import Sequence
from uuid import UUID

from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.jobs.maintenance import release_dead_turn
from pathfinder.persistence.repositories import (
    ChatTurnCancellationRepository,
    ConversationRepository,
)
from pathfinder.platform.errors import TurnStillRunningError
from pathfinder.services.conversations.authz import get_owned_or_404

STOP_POLL_INTERVAL_SECONDS = 0.05
STOP_WAIT_TIMEOUT_SECONDS = 30.0


async def _open_turns(conversation_ids: Sequence[UUID]) -> dict[UUID, UUID]:
    """The turn each of these threads is still writing, keyed by thread.

    A thread whose newest chunk closes the stream is left out.
    """
    if not conversation_ids:
        return {}
    newest = (
        select(ConversationEvent)
        .where(
            ConversationEvent.conversation_id.in_(conversation_ids),
            ConversationEvent.task_id.is_(None),
        )
        .distinct(ConversationEvent.conversation_id)
        .order_by(ConversationEvent.conversation_id, ConversationEvent.id.desc())
    )
    async with async_session_factory() as session:
        rows = (await session.scalars(newest)).all()
    return {
        row.conversation_id: row.turn_id
        for row in rows
        if row.turn_id is not None and row.chunk.get("type") != "done"
    }


async def cancel_in_flight_turn(conversation_id: UUID) -> bool:
    """Ask the worker running the thread's newest turn to stop.

    Reports whether a turn was still in flight to cancel.
    """
    open_turns = await _open_turns([conversation_id])
    if conversation_id not in open_turns:
        return False
    repo = ChatTurnCancellationRepository(session_factory=async_session_factory)
    await repo.request_cancel(
        conversation_id=conversation_id,
        turn_id=open_turns[conversation_id],
    )
    return True


async def stop_turns_and_wait(
    conversation_ids: Sequence[UUID],
    *,
    timeout_seconds: float = STOP_WAIT_TIMEOUT_SECONDS,
) -> list[UUID]:
    """Stop every in-flight turn on these threads and wait for their workers.

    A worker appends to a thread until it reads the stop, so a caller that
    removes the thread waits for the closing chunk first. Reports the threads
    whose worker did not close its turn inside the window.
    """
    repo = ChatTurnCancellationRepository(session_factory=async_session_factory)
    open_turns = await _open_turns(conversation_ids)
    for conversation_id, turn_id in open_turns.items():
        await repo.request_cancel(conversation_id=conversation_id, turn_id=turn_id)
        await release_dead_turn(conversation_id)
    pending = list(open_turns)
    deadline = time.monotonic() + timeout_seconds
    while pending and time.monotonic() < deadline:
        await asyncio.sleep(STOP_POLL_INTERVAL_SECONDS)
        pending = list(await _open_turns(pending))
    return pending


async def stop_turn_before_delete(conversation_id: UUID) -> None:
    """Stop the thread's turn and wait for the worker before the row goes.

    A worker appends to a thread until it reads the stop; removing the row
    under it breaks every write that follows.
    """
    still_running = await stop_turns_and_wait([conversation_id])
    if still_running:
        raise TurnStillRunningError(conversation_id)


async def turn_is_cancelled(*, conversation_id: UUID, turn_id: UUID) -> bool:
    """Whether a stop has been requested for one turn."""
    repo = ChatTurnCancellationRepository(session_factory=async_session_factory)
    return await repo.is_cancelled(conversation_id=conversation_id, turn_id=turn_id)


async def cancel_active_turn(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    user_id: UUID,
) -> None:
    await get_owned_or_404(
        ConversationRepository(session),
        conversation_id,
        user_id,
    )
    if await cancel_in_flight_turn(conversation_id):
        await release_dead_turn(conversation_id)
