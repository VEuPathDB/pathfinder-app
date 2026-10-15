"""One full turn, from the route through the worker, runs under a resolved assistant.

The worker builds the graph from the spec the payload names, so a turn that
completes proves the whole pipeline resolved an assistant rather than naming
PathFinder's graph.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.platform.security import create_user_token
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)

_PROMPT = "hi"
_OK = 200

# A ceiling on a hung turn, not a budget for a fast one: every hop is
# in-process against the mock provider and settles in under a second, so a
# wait near this bound is a deadlock and not a loaded machine.
_DEADLOCK_CEILING_SECONDS = 120.0


async def test_a_completed_turn_records_the_assistant_that_answered(
    app: FastAPI,
    patch_app_db_engine: None,
    authed_user_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb
    conversation_id = uuid4()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies={"Authorization": create_user_token(authed_user_id)},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        post = asyncio.create_task(
            client.post(
                "/api/v1/chat",
                json=chat_post_body(conversation_id, _PROMPT),
                timeout=_DEADLOCK_CEILING_SECONDS,
            ),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(in_memory_jobs),
            timeout=_DEADLOCK_CEILING_SECONDS,
        )
        job = next(
            j for j in in_memory_jobs.jobs.values() if j["task_name"] == "chat_turn:run"
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=_DEADLOCK_CEILING_SECONDS)

    assert response.status_code == _OK
    assert job["args"]["payload"]["assistant_id"] == "pathfinder"

    types = [chunk.get("type") for chunk in parse_sse_body(response.text)]
    assert types.count("done") == 1, "the worker did not finish the turn"

    async with session_maker() as session:
        assistant_id = await session.scalar(
            select(Conversation.assistant_id).where(
                Conversation.id == conversation_id,
            ),
        )
    assert assistant_id == "pathfinder"
