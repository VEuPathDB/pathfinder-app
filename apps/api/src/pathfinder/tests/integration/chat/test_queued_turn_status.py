"""A deferred turn reports "Queued" before the worker writes its first chunk.

Without it the stream carries nothing at all while the job waits, and the tab
shows the same state as a turn that never started.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select

from pathfinder.platform.security import create_user_token
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)

_PROMPT = "hi"


@pytest.fixture
async def chat_client(
    app: FastAPI, authed_user_id: UUID, signed_in_to_veupathdb: None
) -> AsyncIterator[httpx.AsyncClient]:
    del signed_in_to_veupathdb
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"Authorization": create_user_token(authed_user_id)},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        yield client


async def _persisted_events(
    conversation_id: UUID,
) -> list[tuple[UUID | None, dict[str, Any]]]:
    async with async_session_factory() as session:
        rows = (
            await session.scalars(
                select(ConversationEvent)
                .where(ConversationEvent.conversation_id == conversation_id)
                .order_by(ConversationEvent.id),
            )
        ).all()
    return [(row.turn_id, row.chunk) for row in rows]


async def test_the_queued_status_lands_before_the_worker_runs(
    chat_client: httpx.AsyncClient,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """The turn is announced as Queued while its job still waits."""
    del patch_app_db_engine, db_cleaner
    conversation_id = uuid4()

    post = asyncio.create_task(
        chat_client.post(
            "/api/v1/chat",
            json=chat_post_body(conversation_id, _PROMPT),
            timeout=30.0,
        ),
    )
    try:
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(in_memory_jobs),
            timeout=10.0,
        )
        events = await _persisted_events(conversation_id)
        deferred_turn_id = chat_turn_jobs(in_memory_jobs)[0]["args"]["payload"][
            "turn_id"
        ]
    finally:
        post.cancel()
        await asyncio.gather(post, return_exceptions=True)

    assert [chunk["type"] for _, chunk in events] == [
        "user-message",
        "data-turn-status",
    ]
    assert events[-1][1]["data"]["label"] == "Queued"
    # A stop request routes by the last event's turn, so the queued status must
    # carry the turn the worker runs.
    assert str(events[-1][0]) == deferred_turn_id


async def test_the_finished_turn_replays_the_queued_status(
    chat_client: httpx.AsyncClient,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """A reconnecting client reads Queued from the snapshot, then the rest."""
    del patch_app_db_engine, db_cleaner
    conversation_id = uuid4()

    post = asyncio.create_task(
        chat_client.post(
            "/api/v1/chat",
            json=chat_post_body(conversation_id, _PROMPT),
            timeout=30.0,
        ),
    )
    await asyncio.wait_for(
        wait_until_chat_turn_deferred(in_memory_jobs),
        timeout=10.0,
    )
    await run_deferred_chat_turns()
    response = await asyncio.wait_for(post, timeout=30.0)
    assert response.status_code == 200

    snapshot = await chat_client.get(
        f"/api/v1/conversations/{conversation_id}/events/snapshot",
    )
    assert snapshot.status_code == 200
    labels = [
        chunk["data"]["label"]
        for chunk in snapshot.json()["chunks"]
        if chunk["type"] == "data-turn-status"
    ]

    assert labels[0] == "Queued"
    assert labels[1:] != []
