"""``begin_conversation`` refuses a conversation owned by another user."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.errors import NotFoundError
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.begin import begin_conversation


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


async def _make_conversation(session: AsyncSession, owner: User) -> UUID:
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner.id,
        site_id="plasmodb",
        name="Owner kinases",
    )
    session.add(conversation)
    await session.flush()
    await session.commit()
    return conversation.id


async def test_begin_creates_a_conversation_for_a_fresh_id(
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session)
    conversation_id = uuid4()

    result = await begin_conversation(
        session=db_session,
        conversation_id=conversation_id,
        user_id=owner.id,
        site_id="plasmodb",
        assistant_id=PATHFINDER_ASSISTANT_ID,
    )

    assert result.is_new is True
    assert result.conversation.id == conversation_id
    assert result.conversation.user_id == owner.id


async def test_begin_returns_the_existing_conversation_for_its_owner(
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner)

    result = await begin_conversation(
        session=db_session,
        conversation_id=conversation_id,
        user_id=owner.id,
        site_id="plasmodb",
        assistant_id=PATHFINDER_ASSISTANT_ID,
    )

    assert result.is_new is False
    assert result.conversation.id == conversation_id
    assert result.conversation.name == "Owner kinases"


async def test_begin_hides_a_conversation_owned_by_another_user(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    owner = await _make_user(db_session)
    intruder = await _make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner)
    owner_id = owner.id

    with pytest.raises(NotFoundError) as raised:
        await begin_conversation(
            session=db_session,
            conversation_id=conversation_id,
            user_id=intruder.id,
            site_id="plasmodb",
            assistant_id=PATHFINDER_ASSISTANT_ID,
        )

    assert raised.value.status == 404
    await db_session.rollback()
    async with session_maker() as fresh:
        stored = await ConversationRepository(fresh).get_by_id(conversation_id)
    assert stored is not None
    assert stored.user_id == owner_id
    assert stored.name == "Owner kinases"
