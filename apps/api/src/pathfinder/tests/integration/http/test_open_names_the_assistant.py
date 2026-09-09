"""A thread opened through ``/conversations/open`` names the assistant it runs.

The row carries the routing record, so a thread created without an assistant
id is answered by this deployment's own assistant on its first turn.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests.integration.http.conftest import client_for, make_user

_OK = 200
_NOT_FOUND = 404


async def _open(client: httpx.AsyncClient, **extra: str) -> httpx.Response:
    return await client.post(
        "/api/v1/conversations/open",
        json={"siteId": "plasmodb", **extra},
    )


async def _assistant_of(
    session_maker: async_sessionmaker[AsyncSession],
    conversation_id: UUID,
) -> str | None:
    async with session_maker() as session:
        return await session.scalar(
            select(Conversation.assistant_id).where(
                Conversation.id == conversation_id,
            ),
        )


@pytest.fixture
async def api_client(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    signed_in_to_veupathdb: None,
) -> httpx.AsyncClient:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    return client_for(app, owner.id)


async def test_a_thread_opened_without_an_assistant_is_begun_by_this_one(
    api_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with api_client as client:
        opened = await _open(client)
        assert opened.status_code == _OK, opened.text
        conversation_id = UUID(opened.json()["conversationId"])

        begun = await client.post(
            f"/api/v1/conversations/{conversation_id}/begin",
            json={"siteId": "plasmodb"},
        )

    assert begun.status_code == _OK, begun.text
    assert (
        await _assistant_of(session_maker, conversation_id) == PATHFINDER_ASSISTANT_ID
    )


async def test_a_thread_opened_under_a_named_assistant_keeps_it(
    api_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with api_client as client:
        opened = await _open(client, assistantId="site_help")
        assert opened.status_code == _OK, opened.text
        conversation_id = UUID(opened.json()["conversationId"])

        begun = await client.post(
            f"/api/v1/conversations/{conversation_id}/begin",
            json={"siteId": "plasmodb", "assistantId": "site_help"},
        )

    assert begun.status_code == _OK, begun.text
    assert await _assistant_of(session_maker, conversation_id) == "site_help"


async def test_an_unknown_assistant_is_refused_when_the_thread_is_opened(
    api_client: httpx.AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """The refusal lands at creation, so no row is written under a stale id."""
    async with api_client as client:
        opened = await _open(client, assistantId="no_such_assistant")

    assert opened.status_code == _NOT_FOUND, opened.text
    assert opened.json()["code"] == "ASSISTANT_NOT_FOUND"
    async with session_maker() as session:
        rows = await session.execute(select(Conversation.id))
    assert rows.all() == []
