from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from assistant_core.conversation.authz import owned_by_caller
from assistant_core.persistence.models import Conversation, Message
from assistant_core.persistence.repositories.scratchpad import ScratchpadRepository
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories.checkpoint_rows import (
    ChannelRewrite,
    copy_checkpoints,
    rewrite_channels,
)
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.thread_refusals import ForkRefusedError
from pathfinder.services.conversations.fork_copy import (
    EventRewrite,
    copy_conversation_events,
)
from pathfinder.services.conversations.fork_ids import IdMint
from pathfinder.services.conversations.fork_strategy import (
    anchor_snapshot,
    write_forked_strategy,
)
from pathfinder.services.conversations.thread_busy import (
    ThreadBusy,
    claim_settled_thread,
)
from pathfinder.services.conversations.thread_mode import copy_thread_mode
from pathfinder.services.eda.thread_surgery import (
    branch_thread_binding,
    delete_released_document,
)


class ForkError(ValueError):
    """Raised when the fork request references missing or unauthorized rows."""


_REFUSALS = {
    ThreadBusy.LOCKED: (
        "This chat is changing right now. Try the branch again in a moment."
    ),
    ThreadBusy.TURN: (
        "This chat is still answering. Branch it once the reply has finished."
    ),
    ThreadBusy.APPROVAL: (
        "This chat is waiting for your answer to a request. Answer it, then branch."
    ),
    ThreadBusy.TASK: (
        "This chat is running a background task. Branch it once the task has finished."
    ),
}

_COPY_REFUSALS = {
    ThreadBusy.LOCKED: "This conversation is changing right now. Try again in a moment.",
    ThreadBusy.TURN: (
        "This conversation is still answering. Make a copy once the reply has finished."
    ),
    ThreadBusy.APPROVAL: (
        "This conversation is waiting for its owner's answer. Make a copy once it is "
        "answered."
    ),
    ThreadBusy.TASK: (
        "This conversation is running a background task. Make a copy once it has "
        "finished."
    ),
}


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
    return await _thread_from(
        session,
        source=source,
        from_message_id=from_message_id,
        user_id=user_id,
        name=new_name or f"{source.name} (branch)",
        for_another_account=None,
    )


@dataclass(frozen=True)
class CopyTerms:
    rewrite: ChannelRewrite
    keep_owner_reads: bool


async def copy_conversation(
    session: AsyncSession,
    *,
    source: Conversation,
    user_id: UUID,
    terms: CopyTerms,
) -> Conversation:
    """Copy the whole thread into ``user_id``'s account, with no parent link."""
    last = await session.scalar(
        select(Message.id)
        .where(Message.conversation_id == source.id)
        .order_by(desc(Message.created_at))
        .limit(1),
    )
    if last is None:
        msg = "The conversation has no messages to copy"
        raise ForkError(msg)
    return await _thread_from(
        session,
        source=source,
        from_message_id=last,
        user_id=user_id,
        name=f"{source.name} (copy)",
        for_another_account=terms,
    )


async def _thread_from(
    session: AsyncSession,
    *,
    source: Conversation,
    from_message_id: UUID,
    user_id: UUID,
    name: str,
    for_another_account: CopyTerms | None,
) -> Conversation:
    source_conversation_id = source.id
    branch = for_another_account is None
    busy = await claim_settled_thread(session, source_conversation_id)
    if busy is not None:
        raise ForkRefusedError((_REFUSALS if branch else _COPY_REFUSALS)[busy])
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
        name=name,
        assistant_id=source.assistant_id,
        application_id=source.application_id,
        parent_conversation_id=source_conversation_id if branch else None,
        parent_message_id=from_message_id if branch else None,
    )
    session.add(fork)
    await session.flush()
    await copy_thread_mode(
        session,
        source_conversation_id=source_conversation_id,
        target_conversation_id=new_conv_id,
    )

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
        rewrite=EventRewrite(
            note_id_map=note_id_map,
            messages=messages,
            hide_owner_reads=(
                for_another_account is not None
                and not for_another_account.keep_owner_reads
            ),
        ),
    )
    await StrategyRevisionRepository(session).copy_prefix(
        source_conversation_id=source_conversation_id,
        target_conversation_id=new_conv_id,
        cutoff=next_message_ts,
        message_id_map=messages.mapping,
    )
    await copy_checkpoints(
        session,
        source_thread_id=str(source_conversation_id),
        target_thread_id=str(new_conv_id),
        cutoff=next_message_ts,
    )
    if for_another_account is not None:
        await rewrite_channels(
            session, thread_id=str(new_conv_id), rewrite=for_another_account.rewrite
        )
    # The copied log carries the binding states of the turns it holds.
    document = await branch_thread_binding(session, conversation_id=new_conv_id)
    if snapshot is None or source_strategy_row is None:
        return fork
    try:
        await write_forked_strategy(
            session,
            branch=fork,
            snapshot=snapshot,
            strategy_row=source_strategy_row,
            anchor_message_id=UUID(messages.of(str(anchor.id))),
            same_account=branch,
        )
    except Exception:
        await delete_released_document(document)
        raise
    return fork
