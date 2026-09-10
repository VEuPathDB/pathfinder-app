from __future__ import annotations

import asyncio
from uuid import UUID

from assistant_core.conversation.cancellation import turn_is_cancelled
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger

from pathfinder.services.strategies.revision_ops import discard_turn_strategy_writes

CANCEL_POLL_INTERVAL_SECONDS = 1.0

logger = get_logger(__name__)


async def watch_for_cancel(
    *,
    conversation_id: UUID,
    turn_id: UUID,
    cancel_event: asyncio.Event,
) -> None:
    while not cancel_event.is_set():
        try:
            cancelled = await turn_is_cancelled(
                conversation_id=conversation_id,
                turn_id=turn_id,
            )
        except Exception:
            logger.exception(
                "Cancel watcher poll failed",
                conversation_id=str(conversation_id),
                turn_id=str(turn_id),
            )
            return
        if cancelled:
            cancel_event.set()
            return
        try:
            await asyncio.sleep(CANCEL_POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return


async def restore_pre_turn_strategy(
    conversation_id: UUID,
    *,
    pre_turn_revision_id: int | None,
) -> None:
    """Undo a stopped turn's half-written strategy.

    The epilogue that follows reports the revision the thread is back on.
    """
    async with async_session_factory() as session:
        restored = await discard_turn_strategy_writes(
            session,
            conversation_id=conversation_id,
            pre_turn_revision_id=pre_turn_revision_id,
        )
        await session.commit()
    logger.info(
        "stopped turn strategy restored",
        conversation_id=str(conversation_id),
        restored=restored,
    )
