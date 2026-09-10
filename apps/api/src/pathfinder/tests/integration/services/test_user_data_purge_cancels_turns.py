"""A purge stops the turns that are still writing to the threads it removes.

A worker keeps appending chunks to ``conversation_events`` until it is told to
stop, and the rows point at the conversation. The purge therefore cancels every
in-flight turn and waits for the worker before it deletes anything.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.cancellation import turn_is_cancelled
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.graph.stream_events import turn_status_event
from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from pydantic_ai.ui.vercel_ai.response_types import DoneChunk
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.user_data import purge_user_data

_WORKER_TICK_SECONDS = 0.05
_WORKER_MAX_TICKS = 60


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    patch_app_db_engine: None,
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del patch_app_db_engine, db_cleaner
    async with session_maker() as session:
        yield session


async def _thread_with_a_running_turn(
    db_session: AsyncSession,
) -> tuple[UUID, UUID, UUID]:
    owner = User(id=uuid4())
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner.id,
        site_id="plasmodb",
        name="running",
    )
    db_session.add_all([owner, conversation])
    await db_session.flush()
    await db_session.commit()
    turn_id = uuid4()
    await _writer(conversation.id, turn_id).write(
        turn_status_event(label="Working").model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
    )
    return owner.id, conversation.id, turn_id


def _writer(conversation_id: UUID, turn_id: UUID) -> ChatEventWriter:
    return ChatEventWriter(conversation_id=conversation_id, turn_id=turn_id)


async def _worker(conversation_id: UUID, turn_id: UUID) -> bool:
    """Append a chunk per tick until the turn is cancelled, then close it.

    Reports whether the cancellation arrived before the ticks ran out.
    """
    writer = _writer(conversation_id, turn_id)
    for _ in range(_WORKER_MAX_TICKS):
        if await turn_is_cancelled(conversation_id=conversation_id, turn_id=turn_id):
            await writer.write(
                DoneChunk().model_dump(by_alias=True, mode="json", exclude_none=True),
            )
            return True
        await writer.write(
            turn_status_event(label="Working").model_dump(
                by_alias=True,
                mode="json",
                exclude_none=True,
            ),
        )
        await asyncio.sleep(_WORKER_TICK_SECONDS)
    return False


async def _purge(user_id: UUID) -> None:
    async with async_session_factory() as session:
        await purge_user_data(
            session=session,
            user_id=user_id,
            site_id=None,
            delete_wdk=True,
        )


async def _count(model: type[Conversation] | type[ConversationEvent]) -> int:
    async with async_session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_the_worker_stops_before_the_purge_deletes_the_thread(
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del in_memory_jobs
    user_id, conversation_id, turn_id = await _thread_with_a_running_turn(db_session)

    worker = asyncio.create_task(_worker(conversation_id, turn_id))
    await _purge(user_id)

    assert await worker is True
    assert await _count(Conversation) == 0
    assert await _count(ConversationEvent) == 0


async def test_the_purge_asks_the_running_turn_to_stop(
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del in_memory_jobs
    user_id, conversation_id, turn_id = await _thread_with_a_running_turn(db_session)
    seen: list[bool] = []

    async def _observe() -> None:
        for _ in range(_WORKER_MAX_TICKS):
            if await turn_is_cancelled(
                conversation_id=conversation_id,
                turn_id=turn_id,
            ):
                seen.append(True)
                await _writer(conversation_id, turn_id).write(
                    DoneChunk().model_dump(
                        by_alias=True,
                        mode="json",
                        exclude_none=True,
                    ),
                )
                return
            await asyncio.sleep(_WORKER_TICK_SECONDS)

    observer = asyncio.create_task(_observe())
    await _purge(user_id)
    await observer

    assert seen == [True]
    assert await _count(Conversation) == 0
