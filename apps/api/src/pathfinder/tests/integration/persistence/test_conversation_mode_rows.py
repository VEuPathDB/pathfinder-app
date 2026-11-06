from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import ConversationMode, User
from pathfinder.persistence.repositories.conversation_mode import (
    read_thread_mode_row,
    write_thread_mode_row,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.thread_mode import thread_mode_of

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def conversation_id(db_session: AsyncSession) -> UUID:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    thread = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID, id=uuid4(), user_id=user.id
    )
    db_session.add(thread)
    await db_session.commit()
    return thread.id


async def test_a_thread_with_no_row_reads_none(
    db_session: AsyncSession, conversation_id: UUID
) -> None:
    assert (
        await read_thread_mode_row(db_session, conversation_id=conversation_id),
        await thread_mode_of(db_session, conversation_id),
    ) == (None, "auto")


async def test_the_last_written_mode_is_read(
    db_session: AsyncSession, conversation_id: UUID
) -> None:
    await write_thread_mode_row(
        db_session, conversation_id=conversation_id, mode="explore"
    )
    await write_thread_mode_row(
        db_session, conversation_id=conversation_id, mode="build"
    )
    await db_session.commit()
    assert (
        await read_thread_mode_row(db_session, conversation_id=conversation_id)
        == "build"
    )


async def test_deleting_the_thread_deletes_its_mode(
    db_session: AsyncSession, conversation_id: UUID
) -> None:
    await write_thread_mode_row(
        db_session, conversation_id=conversation_id, mode="explore"
    )
    await db_session.commit()
    await db_session.execute(
        delete(Conversation).where(Conversation.id == conversation_id)
    )
    await db_session.commit()
    rows = await db_session.scalar(
        select(func.count())
        .select_from(ConversationMode)
        .where(ConversationMode.conversation_id == conversation_id)
    )
    assert rows == 0
