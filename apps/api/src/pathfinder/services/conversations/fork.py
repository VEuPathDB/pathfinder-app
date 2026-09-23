from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from assistant_core.conversation.authz import owned_by_caller
from assistant_core.persistence.models import BackgroundTask, Conversation, Message
from assistant_core.persistence.repositories.background_tasks import (
    ACTIVE_TASK_STATES,
)
from assistant_core.persistence.repositories.scratchpad import ScratchpadRepository
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.errors import ForkRefusedError
from pathfinder.services.conversations.fork_copy import (
    copy_checkpoint_state,
    copy_conversation_events,
)
from pathfinder.services.conversations.fork_ids import IdMint
from pathfinder.services.conversations.fork_strategy import (
    anchor_snapshot,
    write_forked_strategy,
)
from pathfinder.services.eda.thread_surgery import branch_thread_binding


class ForkError(ValueError):
    """Raised when the fork request references missing or unauthorized rows."""


async def _refuse_while_a_task_runs(
    session: AsyncSession,
    *,
    source_conversation_id: UUID,
    cutoff_ts: datetime | None,
) -> None:
    """Refuse a branch whose checkpoints park a call no worker will answer.

    The worker resumes a durable call on the thread that deferred it, so a
    copy of that checkpoint stays mid-turn for good.
    """
    stmt = select(BackgroundTask.id).where(
        BackgroundTask.conversation_id == source_conversation_id,
        BackgroundTask.status.in_(ACTIVE_TASK_STATES),
    )
    if cutoff_ts is not None:
        stmt = stmt.where(BackgroundTask.created_at < cutoff_ts)
    running = await session.scalar(stmt.limit(1))
    if running is None:
        return
    msg = (
        "This chat is running a background task. Branch it once the task has finished."
    )
    raise ForkRefusedError(msg)


async def fork_conversation(
    session: AsyncSession,
    *,
    source_conversation_id: UUID,
    from_message_id: UUID,
    user_id: UUID,
    new_name: str | None = None,
) -> Conversation:
    """Create a fork. ``from_message_id`` is the last message copied over."""
    source = await session.scalar(
        select(Conversation).where(Conversation.id == source_conversation_id),
    )
    if source is None or not owned_by_caller(source, user_id):
        msg = "Source conversation not found"
        raise ForkError(msg)
    source_strategy_row = await session.get(
        ConversationStrategy,
        source_conversation_id,
    )

    anchor = await session.scalar(
        select(Message).where(
            Message.id == from_message_id,
            Message.conversation_id == source_conversation_id,
        ),
    )
    if anchor is None:
        msg = "Fork anchor message not found in source conversation"
        raise ForkError(msg)

    prefix_rows = await session.scalars(
        select(Message)
        .where(
            Message.conversation_id == source_conversation_id,
            Message.created_at <= anchor.created_at,
        )
        .order_by(asc(Message.created_at)),
    )
    prefix = list(prefix_rows)

    next_message_ts = await session.scalar(
        select(Message.created_at)
        .where(
            Message.conversation_id == source_conversation_id,
            Message.created_at > anchor.created_at,
        )
        .order_by(asc(Message.created_at))
        .limit(1),
    )
    await _refuse_while_a_task_runs(
        session,
        source_conversation_id=source_conversation_id,
        cutoff_ts=next_message_ts,
    )
    snapshot = await anchor_snapshot(
        session,
        source_conversation_id=source_conversation_id,
        anchor=anchor,
        strategy_row=source_strategy_row,
    )

    new_conv_id = uuid4()
    fork = Conversation(
        id=new_conv_id,
        user_id=user_id,
        site_id=source.site_id,
        name=new_name or f"{source.name} (branch)",
        assistant_id=source.assistant_id,
        application_id=source.application_id,
        parent_conversation_id=source_conversation_id,
        parent_message_id=from_message_id,
    )
    session.add(fork)
    await session.flush()

    # Notes copy first so the id map is ready when the chunk copy rewrites
    # tool-call payloads. Checkpoint blobs keep the source note ids.
    scratchpad_repo = ScratchpadRepository(session)
    note_id_map = await scratchpad_repo.copy_notes_for_fork(
        source_conversation_id=source_conversation_id,
        target_conversation_id=new_conv_id,
        cutoff=next_message_ts,
    )

    messages = IdMint()
    # Each copy keeps its source created_at, because revert cuts on that value.
    for src_msg in prefix:
        session.add(
            Message(
                id=UUID(messages.of(str(src_msg.id))),
                conversation_id=new_conv_id,
                role=src_msg.role,
                metadata_=dict(src_msg.metadata_ or {}),
                created_at=src_msg.created_at,
            ),
        )

    await session.flush()
    await copy_conversation_events(
        session,
        source_conversation_id=source_conversation_id,
        new_conversation_id=new_conv_id,
        cutoff_ts=next_message_ts,
        note_id_map=note_id_map,
        messages=messages,
    )
    await StrategyRevisionRepository(session).copy_prefix(
        source_conversation_id=source_conversation_id,
        target_conversation_id=new_conv_id,
        cutoff=next_message_ts,
        message_id_map=messages.mapping,
    )
    if snapshot is not None and source_strategy_row is not None:
        await write_forked_strategy(
            session,
            branch=fork,
            snapshot=snapshot,
            strategy_row=source_strategy_row,
            new_conversation_id=new_conv_id,
            anchor_message_id=UUID(messages.of(str(anchor.id))),
        )
    await copy_checkpoint_state(
        session,
        source_thread_id=str(source_conversation_id),
        new_thread_id=str(new_conv_id),
        cutoff_ts=next_message_ts,
    )
    # The copied log carries the binding states of the turns it holds.
    await branch_thread_binding(session, conversation_id=new_conv_id)
    return fork
