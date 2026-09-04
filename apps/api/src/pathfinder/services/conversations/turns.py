"""The reads and writes one assistant turn makes on the thread it runs on."""

from __future__ import annotations

from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import DBSessionFactory, async_session_factory

from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)


async def load_conversation(conversation_id: UUID) -> Conversation | None:
    """The thread a turn runs on, or None when no such thread exists."""
    async with async_session_factory() as session:
        return await ConversationRepository(session).get_by_id(conversation_id)


async def name_conversation_if_unnamed(conversation_id: UUID, *, title: str) -> bool:
    """Give the thread a generated title, keeping any name it already holds.

    Reports whether the title was written.
    """
    async with async_session_factory() as session:
        repo = ConversationRepository(session)
        conversation = await repo.get_by_id(conversation_id)
        if conversation is None or conversation.name:
            return False
        await repo.update_conversation(conversation_id, ConversationUpdate(name=title))
        await session.commit()
    return True


async def turn_start_revision_id(conversation_id: UUID) -> int | None:
    """The strategy snapshot the thread holds as the turn opens."""
    async with async_session_factory() as session:
        latest = await StrategyRevisionRepository(session).latest(conversation_id)
    return None if latest is None else latest.id


async def name_turn_strategy_revision(
    session_factory: DBSessionFactory,
    *,
    conversation_id: UUID,
    message_id: UUID,
) -> None:
    """Record which message the strategy the turn left behind belongs to."""
    async with session_factory() as session:
        await StrategyRevisionRepository(session).name_latest(
            conversation_id,
            message_id=message_id,
        )
        await session.commit()
