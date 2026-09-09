"""A regenerate replays the thread and ends it at the same user message.

The log holds one envelope per message id. A client rebuilds its thread from
the log, and a repeated id names two nodes for one message.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import httpx
from assistant_core.persistence.models import Conversation, ConversationEvent
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
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


async def _post_turn(
    client: httpx.AsyncClient,
    connector: InMemoryConnector,
    body: dict[str, Any],
) -> None:
    """POST one turn and return once its job is deferred; the tail is dropped."""
    before = len(chat_jobs(connector))
    post = asyncio.create_task(
        client.post("/api/v1/chat", json=body, timeout=60.0),
    )
    try:
        await asyncio.wait_for(
            _wait_for_new_chat_job(connector, before),
            timeout=30.0,
        )
    finally:
        post.cancel()
        await asyncio.gather(post, return_exceptions=True)


async def _user_message_ids(
    session: AsyncSession,
    conversation_id: UUID,
) -> list[str]:
    rows = (
        await session.scalars(
            select(ConversationEvent)
            .where(
                ConversationEvent.conversation_id == conversation_id,
                ConversationEvent.chunk["type"].astext == "user-message",
            )
            .order_by(ConversationEvent.id),
        )
    ).all()
    return [str(row.chunk["message"]["id"]) for row in rows]


async def _make_conversation(session: AsyncSession, owner_id: UUID) -> UUID:
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner_id,
        site_id="plasmodb",
        name="regenerate fixture",
    )
    session.add(conversation)
    await session.flush()
    await session.commit()
    return conversation.id


async def test_a_regenerate_writes_no_second_user_message_envelope(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner.id)
    message_id = str(uuid4())

    async with client_for(app, owner.id) as client:
        await _post_turn(
            client,
            in_memory_jobs,
            chat_body(conversation_id, message_id=message_id),
        )
        await _post_turn(
            client,
            in_memory_jobs,
            chat_body(
                conversation_id,
                message_id=message_id,
                trigger="regenerate-message",
            ),
        )

    assert await _user_message_ids(db_session, conversation_id) == [message_id]
    assert len(chat_jobs(in_memory_jobs)) == 2


async def test_a_replayed_submit_writes_no_second_user_message_envelope(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    """The id decides, not the trigger the client names."""
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner.id)
    message_id = str(uuid4())
    body = chat_body(conversation_id, message_id=message_id)

    async with client_for(app, owner.id) as client:
        await _post_turn(client, in_memory_jobs, body)
        await _post_turn(client, in_memory_jobs, body)

    assert await _user_message_ids(db_session, conversation_id) == [message_id]


async def test_two_user_messages_each_keep_their_envelope(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    owner = await make_user(db_session)
    conversation_id = await _make_conversation(db_session, owner.id)
    first = str(uuid4())
    second = str(uuid4())

    async with client_for(app, owner.id) as client:
        await _post_turn(
            client,
            in_memory_jobs,
            chat_body(conversation_id, message_id=first),
        )
        await _post_turn(
            client,
            in_memory_jobs,
            chat_body(conversation_id, message_id=second),
        )

    assert await _user_message_ids(db_session, conversation_id) == [first, second]
