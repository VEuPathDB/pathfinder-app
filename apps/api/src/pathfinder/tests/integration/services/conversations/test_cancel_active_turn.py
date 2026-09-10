"""A stop pressed while a turn is queued reaches the turn the worker polls."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from assistant_core.conversation.cancellation import cancel_active_turn
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.graph.stream_events import turn_status_event
from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories.chat_turn_cancellations import (
    ChatTurnCancellationRepository,
)
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del patch_app_db_engine, db_cleaner
    async with session_maker() as session:
        yield session


async def test_a_stop_while_queued_cancels_the_turn_the_worker_runs(
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del in_memory_jobs
    owner = User(id=uuid4())
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner.id,
        site_id="plasmodb",
        name="queued",
    )
    db_session.add_all([owner, conversation])
    await db_session.flush()
    await db_session.commit()
    conversation_id = conversation.id
    user_message_id = uuid4()
    worker_turn_id = uuid4()

    await ChatEventWriter(
        conversation_id=conversation_id,
        turn_id=user_message_id,
    ).write(
        user_message_chunk(
            message_id=str(user_message_id),
            parts=[{"type": "text", "text": "hi"}],
        ),
    )
    await ChatEventWriter(
        conversation_id=conversation_id,
        turn_id=worker_turn_id,
    ).write(
        turn_status_event(label="Queued").model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
    )

    await cancel_active_turn(
        db_session,
        conversation_id=conversation_id,
        user_id=owner.id,
    )

    repo = ChatTurnCancellationRepository(session_factory=async_session_factory)
    assert (
        await repo.is_cancelled(
            conversation_id=conversation_id,
            turn_id=worker_turn_id,
        )
        is True
    )
    assert (
        await repo.is_cancelled(
            conversation_id=conversation_id,
            turn_id=user_message_id,
        )
        is False
    )
