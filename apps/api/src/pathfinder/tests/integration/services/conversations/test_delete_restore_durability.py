"""Delete, dismiss and restore are durable when the service call returns.

The client refetches the sidebar as soon as the response arrives, and the
session dependency commits only after the response is sent, so a write that
waits for that teardown is invisible to the refetch.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.service import ConversationService


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


async def _make_user(session: AsyncSession) -> User:
    user = User(id=uuid4())
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def _make_conversation(
    session: AsyncSession,
    owner: User,
    *,
    wdk_strategy_id: int | None = None,
    dismissed: bool = False,
) -> UUID:
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner.id,
        site_id="plasmodb",
        name="Owner kinases",
        dismissed_at=datetime.now(UTC) if dismissed else None,
    )
    session.add(conversation)
    await session.flush()
    if wdk_strategy_id is not None:
        session.add(
            ConversationStrategy(
                conversation_id=conversation.id,
                wdk_strategy_id=wdk_strategy_id,
            ),
        )
        await session.flush()
    await session.commit()
    return conversation.id


async def test_delete_is_visible_to_the_next_request(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    owner = await _make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner)

    await ConversationService(db_session).delete(
        conversation_id,
        owner.id,
        delete_from_wdk=False,
        cascade=False,
    )

    async with session_maker() as fresh:
        assert await ConversationRepository(fresh).get_by_id(conversation_id) is None


async def test_dismiss_of_a_wdk_linked_chat_is_visible_to_the_next_request(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """Delete without ``deleteFromWdk`` soft-deletes and leaves WDK alone."""
    owner = await _make_user(db_session)
    conversation_id = await _make_conversation(
        db_session,
        owner,
        wdk_strategy_id=555,
    )

    await ConversationService(db_session).delete(
        conversation_id,
        owner.id,
        delete_from_wdk=False,
        cascade=False,
    )

    async with session_maker() as fresh:
        stored = await ConversationRepository(fresh).get_by_id(conversation_id)
    assert stored is not None
    assert stored.dismissed_at is not None


async def test_restore_is_visible_to_the_next_request(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    owner = await _make_user(db_session)
    conversation_id = await _make_conversation(
        db_session,
        owner,
        wdk_strategy_id=555,
        dismissed=True,
    )

    await ConversationService(db_session).restore(conversation_id, owner.id)

    async with session_maker() as fresh:
        stored = await ConversationRepository(fresh).get_by_id(conversation_id)
    assert stored is not None
    assert stored.dismissed_at is None
