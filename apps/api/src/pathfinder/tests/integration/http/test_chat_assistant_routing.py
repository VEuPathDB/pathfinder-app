"""A chat turn is routed to an assistant, and the thread records which one.

The conversation row is the routing record: the worker resolves the same
assistant every later turn, so a thread cannot change architecture mid-flight.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.conversation import assistant_routing
from pathfinder.tests.integration.http.conftest import (
    chat_body,
    chat_jobs,
    client_for,
    ends_at_first_frame,
    make_user,
)

_CONFLICT = 409
_NOT_FOUND = 404
_OK = 200


async def _defer_one_turn(
    client: httpx.AsyncClient,
    body: dict[str, Any],
    connector: InMemoryConnector,
) -> dict[str, Any]:
    """POST one turn and return its job row.

    The route defers the job before it answers, so the status line is enough.
    """
    before = len(chat_jobs(connector))
    response = await client.post("/api/v1/chat", json=body, timeout=60.0)
    assert response.status_code == _OK
    jobs = chat_jobs(connector)
    assert len(jobs) > before, "the served turn deferred no job"
    return jobs[-1]


async def _post_chat(client: httpx.AsyncClient, body: dict[str, Any]) -> int:
    response = await client.post("/api/v1/chat", json=body, timeout=60.0)
    return response.status_code


async def _assistant_of(
    session_maker: async_sessionmaker[AsyncSession],
    conversation_id: UUID,
) -> str | None:
    async with session_maker() as session:
        found = await session.scalars(
            select(Conversation.assistant_id).where(
                Conversation.id == conversation_id,
            ),
        )
        return found.one_or_none()


async def test_a_turn_creates_the_thread_under_the_default_assistant(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    body = chat_body(uuid4())

    async with client_for(ends_at_first_frame(app), owner.id) as client:
        job = await _defer_one_turn(client, body, in_memory_jobs)

    conversation_id = UUID(body["conversationId"])
    assert await _assistant_of(session_maker, conversation_id) == "pathfinder"
    assert job["args"]["payload"]["assistant_id"] == "pathfinder"


async def test_a_turn_naming_the_thread_s_assistant_is_served(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    conversation = Conversation(
        user_id=owner.id,
        assistant_id="pathfinder",
        site_id="plasmodb",
        name="kinases",
    )
    db_session.add(conversation)
    await db_session.flush()
    await db_session.commit()
    body = {**chat_body(conversation.id), "assistantId": "pathfinder"}

    async with client_for(ends_at_first_frame(app), owner.id) as client:
        job = await _defer_one_turn(client, body, in_memory_jobs)

    assert job["args"]["payload"]["assistant_id"] == "pathfinder"
    assert await _assistant_of(session_maker, conversation.id) == "pathfinder"


async def test_an_unknown_assistant_is_refused_with_404(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    body = {**chat_body(uuid4()), "assistantId": "no_such_assistant"}

    async with client_for(ends_at_first_frame(app), owner.id) as client:
        status = await _post_chat(client, body)

    assert status == _NOT_FOUND
    assert chat_jobs(in_memory_jobs) == []


async def test_naming_another_assistant_on_an_existing_thread_is_refused(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    conversation = Conversation(
        user_id=owner.id,
        assistant_id="pathfinder",
        site_id="plasmodb",
        name="kinases",
    )
    db_session.add(conversation)
    await db_session.flush()
    await db_session.commit()
    body = {**chat_body(conversation.id), "assistantId": "site_help"}

    async with client_for(ends_at_first_frame(app), owner.id) as client:
        status = await _post_chat(client, body)

    assert status == _CONFLICT
    assert chat_jobs(in_memory_jobs) == []
    assert await _assistant_of(session_maker, conversation.id) == "pathfinder"


async def test_a_thread_created_under_another_assistant_mid_dispatch_is_refused(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    """The row wins: the insert loses the race, so the turn is not deferred."""
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    conversation_id = uuid4()
    body = chat_body(conversation_id)

    async def _resolve_none(_conversation_id: UUID) -> str | None:
        """The read a concurrent first turn would have raced."""
        conversation = Conversation(
            id=conversation_id,
            user_id=owner.id,
            assistant_id="site_help",
            site_id="plasmodb",
            name="raced",
        )
        db_session.add(conversation)
        await db_session.flush()
        await db_session.commit()
        return None

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(assistant_routing, "conversation_assistant_id", _resolve_none)
        async with client_for(ends_at_first_frame(app), owner.id) as client:
            status = await _post_chat(client, body)

    assert status == _CONFLICT
    assert chat_jobs(in_memory_jobs) == []
