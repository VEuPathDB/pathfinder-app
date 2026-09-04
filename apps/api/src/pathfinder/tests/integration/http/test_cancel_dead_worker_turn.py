"""Stop ends a turn whose worker is gone, instead of waiting for maintenance.

A cancel request is a row a live worker polls. A worker the kernel killed polls
nothing, so the request alone leaves the turn running forever in the UI.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.tests.integration.http.conftest import client_for, make_user
from pathfinder.tests.integration.jobs._dead_worker import (
    TOOL_CALL_ID,
    dead_age,
    dead_window_seconds,
    fresh_beat_age,
    open_a_tool_call,
    stage_chat_turn_job,
    starved_age,
    turn_chunks,
)

_NO_CONTENT = 204


async def _make_conversation(session: AsyncSession, owner_id: UUID) -> UUID:
    conversation = Conversation(user_id=owner_id, site_id="plasmodb", name="stop me")
    session.add(conversation)
    await session.flush()
    await session.commit()
    return conversation.id


async def test_stop_on_a_dead_worker_ends_the_turn_and_finishes_the_job(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner.id)
    turn_id = uuid4()
    await open_a_tool_call(conversation_id, turn_id)
    job_id = await stage_chat_turn_job(
        in_memory_jobs,
        user_id=owner.id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        heartbeat_age_seconds=dead_age(),
    )

    async with client_for(app, owner.id) as client:
        response = await client.post(f"/api/v1/conversations/{conversation_id}/cancel")

    assert response.status_code == _NO_CONTENT
    assert in_memory_jobs.jobs[job_id]["status"] == "failed"
    chunks = await turn_chunks(conversation_id)
    assert [chunk["type"] for chunk in chunks[-5:]] == [
        "tool-output-error",
        "error",
        "data-turn-failed",
        "finish",
        "done",
    ]
    assert chunks[-5]["toolCallId"] == TOOL_CALL_ID


async def test_stop_on_a_live_worker_only_asks(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner.id)
    turn_id = uuid4()
    await open_a_tool_call(conversation_id, turn_id)
    job_id = await stage_chat_turn_job(
        in_memory_jobs,
        user_id=owner.id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        heartbeat_age_seconds=fresh_beat_age(),
    )

    async with client_for(app, owner.id) as client:
        response = await client.post(f"/api/v1/conversations/{conversation_id}/cancel")

    assert response.status_code == _NO_CONTENT
    assert in_memory_jobs.jobs[job_id]["status"] == "doing"
    assert [chunk["type"] for chunk in await turn_chunks(conversation_id)] == [
        "start",
        "tool-input-start",
        "tool-input-available",
    ]


async def test_stop_on_a_starved_but_live_worker_only_asks(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """Stop leaves the turn alone while the last beat is inside the window."""
    del patch_app_db_engine
    owner = await make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner.id)
    turn_id = uuid4()
    await open_a_tool_call(conversation_id, turn_id)
    starved = starved_age()
    assert 0 < starved < dead_window_seconds()
    job_id = await stage_chat_turn_job(
        in_memory_jobs,
        user_id=owner.id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        heartbeat_age_seconds=starved,
    )

    async with client_for(app, owner.id) as client:
        response = await client.post(f"/api/v1/conversations/{conversation_id}/cancel")

    assert response.status_code == _NO_CONTENT
    assert in_memory_jobs.jobs[job_id]["status"] == "doing"
    assert [chunk["type"] for chunk in await turn_chunks(conversation_id)] == [
        "start",
        "tool-input-start",
        "tool-input-available",
    ]
