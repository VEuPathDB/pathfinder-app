from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from uuid import UUID

from assistant_core.conversation.authz import owned_by_caller
from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    ConversationEvent,
    Message,
)
from assistant_core.persistence.repositories.scratchpad import ScratchpadRepository
from assistant_core.platform.logging import get_logger
from sqlalchemy import (
    CursorResult,
    DateTime,
    bindparam,
    delete,
    literal,
    select,
    text,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import StrategyRevisionView
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.services.eda.thread_surgery import (
    logs_a_binding,
    restore_thread_binding,
)
from pathfinder.services.strategies.revision_ops import (
    materialize_revision,
    revision_at_message,
)

logger = get_logger(__name__)


class RevertError(ValueError):
    """Raised when the revert request references missing or unauthorized rows."""


def _rows(result: object) -> int:
    return cast("CursorResult[object]", result).rowcount or 0


def _strategy_state(
    snapshot: StrategyRevisionView | None,
    *,
    cutoff_ts: datetime,
    had_history: bool,
) -> Literal["snapshot", "cleared", "unknown"]:
    """What the strategy must become for the surviving transcript to be true.

    A thread with no history at all predates the revision store, so the
    strategy is left where it is rather than deleted on a guess.
    """
    if snapshot is not None and snapshot.created_at < cutoff_ts:
        return "snapshot"
    if had_history:
        return "cleared"
    return "unknown"


async def revert_conversation_to_message(
    session: AsyncSession,
    *,
    conversation_id: UUID,
    target_message_id: UUID,
    user_id: UUID,
) -> None:
    conv = await session.scalar(
        select(Conversation).where(Conversation.id == conversation_id),
    )
    if conv is None or not owned_by_caller(conv, user_id):
        logger.warning(
            "revert: conversation lookup failed",
            conversation_id=str(conversation_id),
            target_message_id=str(target_message_id),
            user_id=str(user_id),
            row_exists=conv is not None,
            owner_match=conv is not None and owned_by_caller(conv, user_id),
        )
        msg = "Conversation not found"
        raise RevertError(msg)

    target = await session.scalar(
        select(Message).where(
            Message.id == target_message_id,
            Message.conversation_id == conversation_id,
        ),
    )
    if target is None:
        wrong_conv_owner = await session.scalar(
            select(Message.conversation_id).where(
                Message.id == target_message_id,
            ),
        )
        if wrong_conv_owner is not None:
            logger.warning(
                "revert: target message not in conversation",
                conversation_id=str(conversation_id),
                target_message_id=str(target_message_id),
                message_belongs_to=str(wrong_conv_owner),
            )
            msg = "Target message not found"
            raise RevertError(msg)
        # Never persisted (turn errored, or send rejected before insert): the
        # server is already at the pre-message state, so revert is a no-op.
        logger.info(
            "revert: target message never persisted; no-op",
            conversation_id=str(conversation_id),
            target_message_id=str(target_message_id),
        )
        return
    if target.role != "user":
        logger.warning(
            "revert: target is not user-authored",
            conversation_id=str(conversation_id),
            target_message_id=str(target_message_id),
            actual_role=target.role,
        )
        msg = "Can only revert to a user-authored message"
        raise RevertError(msg)

    cutoff_ts = target.created_at
    thread_id = str(conversation_id)
    # Read before the cut: the target message is one of the rows it deletes.
    revisions = StrategyRevisionRepository(session)
    snapshot = await revision_at_message(session, message=target)
    had_history = await revisions.has_any(conversation_id)
    logged_a_binding = await logs_a_binding(session, conversation_id=conversation_id)

    # Cut on (created_at, id) so timestamp ties delete deterministically
    # instead of over-deleting siblings that share the target's created_at.
    deleted_messages = _rows(
        await session.execute(
            delete(Message).where(
                Message.conversation_id == conversation_id,
                tuple_(Message.created_at, Message.id)
                >= tuple_(literal(cutoff_ts), literal(target_message_id)),
            ),
        )
    )
    deleted_notes = await ScratchpadRepository(session).delete_notes_from(
        conversation_id=conversation_id,
        cutoff=cutoff_ts,
    )
    deleted_events = _rows(
        await session.execute(
            delete(ConversationEvent).where(
                ConversationEvent.conversation_id == conversation_id,
                ConversationEvent.emitted_at >= cutoff_ts,
            ),
        )
    )
    deleted_tasks = _rows(
        await session.execute(
            delete(BackgroundTask).where(
                BackgroundTask.conversation_id == conversation_id,
                BackgroundTask.created_at >= cutoff_ts,
            ),
        )
    )

    writes_stmt = text(
        """
        DELETE FROM checkpoint_writes w
        USING checkpoints c
        WHERE w.thread_id = c.thread_id
          AND w.checkpoint_ns = c.checkpoint_ns
          AND w.checkpoint_id = c.checkpoint_id
          AND c.thread_id = :thread_id
          AND (c.checkpoint->>'ts')::timestamptz >= :cutoff
        """,
    ).bindparams(bindparam("cutoff", type_=DateTime(timezone=True)))
    deleted_writes = _rows(
        await session.execute(
            writes_stmt,
            {"thread_id": thread_id, "cutoff": cutoff_ts},
        )
    )

    checkpoints_stmt = text(
        """
        DELETE FROM checkpoints
        WHERE thread_id = :thread_id
          AND (checkpoint->>'ts')::timestamptz >= :cutoff
        """,
    ).bindparams(bindparam("cutoff", type_=DateTime(timezone=True)))
    deleted_checkpoints = _rows(
        await session.execute(
            checkpoints_stmt,
            {"thread_id": thread_id, "cutoff": cutoff_ts},
        )
    )

    deleted_revisions = await revisions.delete_at_or_after(
        conversation_id,
        moment=cutoff_ts,
    )
    restored = _strategy_state(snapshot, cutoff_ts=cutoff_ts, had_history=had_history)
    if restored == "snapshot" and snapshot is not None:
        await materialize_revision(session, conversation=conv, revision=snapshot)
    elif restored == "cleared":
        await ConversationRepository(session).clear_strategy(conversation_id)

    # The surviving log names the binding the remaining transcript describes.
    await restore_thread_binding(
        session,
        conversation_id=conversation_id,
        logged=logged_a_binding,
    )

    logger.info(
        "conversation reverted to message",
        conversation_id=thread_id,
        target_message_id=str(target_message_id),
        deleted_messages=deleted_messages,
        deleted_notes=deleted_notes,
        deleted_events=deleted_events,
        deleted_tasks=deleted_tasks,
        deleted_checkpoints=deleted_checkpoints,
        deleted_checkpoint_writes=deleted_writes,
        deleted_strategy_revisions=deleted_revisions,
        strategy=restored,
    )
