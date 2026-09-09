"""A chat turn is deferred under a per-conversation lock.

The worker runs several jobs at once, and every turn for one conversation
writes the same LangGraph checkpoint thread, so two turns for that
conversation must never run together.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests.integration.http.conftest import (
    chat_body,
    chat_jobs,
    client_for,
    make_user,
)


async def _wait_for_new_chat_job(
    connector: InMemoryConnector,
    before: int,
) -> dict[str, Any]:
    while True:
        jobs = chat_jobs(connector)
        if len(jobs) > before:
            return jobs[-1]
        await asyncio.sleep(0.02)


async def _defer_one_turn(
    client: httpx.AsyncClient,
    conversation_id: UUID,
    connector: InMemoryConnector,
) -> dict[str, Any]:
    """POST one turn and return its job row; the SSE tail is abandoned."""
    before = len(chat_jobs(connector))
    post = asyncio.create_task(
        client.post(
            "/api/v1/chat",
            json=chat_body(conversation_id),
            timeout=60.0,
        ),
    )
    try:
        return await asyncio.wait_for(
            _wait_for_new_chat_job(connector, before),
            timeout=30.0,
        )
    finally:
        post.cancel()
        await asyncio.gather(post, return_exceptions=True)


async def _make_conversation(session: AsyncSession, owner_id: UUID, name: str) -> UUID:
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner_id,
        site_id="plasmodb",
        name=name,
    )
    session.add(conversation)
    await session.flush()
    await session.commit()
    return conversation.id


async def test_the_deferred_turn_carries_the_conversation_lock(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner.id, "Owner kinases")

    async with client_for(app, owner.id) as client:
        job = await _defer_one_turn(client, conversation_id, in_memory_jobs)

    assert job["lock"] == str(conversation_id)
    assert job["queue_name"] == "chat_turn"


async def test_the_lock_groups_turns_by_conversation(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    """Two turns on one conversation share a lock; another conversation differs."""
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    first = await _make_conversation(db_session, owner.id, "first")
    second = await _make_conversation(db_session, owner.id, "second")

    async with client_for(app, owner.id) as client:
        await _defer_one_turn(client, first, in_memory_jobs)
        await _defer_one_turn(client, first, in_memory_jobs)
        await _defer_one_turn(client, second, in_memory_jobs)

    locks = [job["lock"] for job in chat_jobs(in_memory_jobs)]
    assert locks.count(str(first)) == 2
    assert locks.count(str(second)) == 1
