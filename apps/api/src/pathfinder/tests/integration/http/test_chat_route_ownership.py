"""POST /api/v1/chat refuses a conversation owned by another user."""

from __future__ import annotations

from uuid import UUID

from assistant_core.persistence.models import Conversation, Message
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests.integration.http.conftest import (
    chat_body,
    chat_jobs,
    client_for,
    ends_at_first_frame,
    make_user,
)


async def _count_messages(
    session_maker: async_sessionmaker[AsyncSession],
    conversation_id: UUID,
) -> int:
    async with session_maker() as session:
        found = await session.execute(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id),
        )
        return found.scalar_one()


async def test_chat_rejects_a_conversation_owned_by_another_user(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    intruder = await make_user(db_session)
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner.id,
        site_id="plasmodb",
        name="Owner kinases",
    )
    db_session.add(conversation)
    await db_session.flush()
    await db_session.commit()

    async with client_for(ends_at_first_frame(app), intruder.id) as client:
        response = await client.post(
            "/api/v1/chat", json=chat_body(conversation.id), timeout=60.0
        )

    assert await _count_messages(session_maker, conversation.id) == 0, (
        "a non-owner's chat POST wrote a message into the owner's conversation"
    )
    assert chat_jobs(in_memory_jobs) == [], (
        "a non-owner's chat POST deferred a turn on the owner's thread"
    )
    assert response.status_code == 404, (
        f"POST /api/v1/chat must answer 404 for a non-owner; got {response.status_code}"
    )
