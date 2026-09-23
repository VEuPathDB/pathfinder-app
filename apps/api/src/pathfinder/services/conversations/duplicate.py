"""A copy of a thread: its strategy, its messages and its event log."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from assistant_core.conversation.authz import get_visible_conversation
from assistant_core.persistence.repositories.message import MessagesRepository
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories import ConversationRepository


@dataclass(frozen=True)
class DuplicatedConversation:
    id: UUID
    name: str


async def duplicate_conversation(
    session: AsyncSession, conversation_id: UUID, user_id: UUID
) -> DuplicatedConversation:
    """Copy a thread the user can see, and commit the copy."""
    repo = ConversationRepository(session)
    source = await get_visible_conversation(repo, conversation_id, user_id)
    source_strategy = await repo.get_strategy(conversation_id)
    msg_repo = MessagesRepository(session)
    new_conv = await repo.create(
        user_id=user_id,
        site_id=source.site_id,
        assistant_id=source.assistant_id,
        name=f"Copy of {source.name}" if source.name else "Conversation (copy)",
    )
    # Carry the strategy over (topology + params). WDK step ids are dropped
    # so the copy re-syncs as its own fresh WDK strategy instead of sharing
    # the source's steps; wdk_strategy_id stays None for the same reason.
    copied_ast = dict(source_strategy.strategy_ast)
    copied_ast.pop("wdkStepIds", None)
    copied_ast.pop("wdk_step_ids", None)
    if copied_ast:
        copied_ast["name"] = new_conv.name
        session.add(
            ConversationStrategy(
                conversation_id=new_conv.id,
                strategy_ast=copied_ast,
            ),
        )
    for row in await msg_repo.list_messages_for_conversation(conversation_id):
        await msg_repo.insert_message(
            message_id=uuid4(),
            conversation_id=new_conv.id,
            role=row.role,
            metadata=row.metadata_,
        )
    await session.execute(
        text(
            """
            INSERT INTO conversation_events (
                conversation_id, turn_id, task_id, chunk
            )
            SELECT :dst, turn_id, task_id, chunk
            FROM conversation_events
            WHERE conversation_id = :src
            ORDER BY id ASC
            """,
        ),
        {"src": str(conversation_id), "dst": str(new_conv.id)},
    )
    await session.commit()
    return DuplicatedConversation(id=new_conv.id, name=new_conv.name)
