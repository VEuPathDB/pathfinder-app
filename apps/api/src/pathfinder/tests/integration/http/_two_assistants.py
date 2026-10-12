"""Driving one chat turn over the HTTP route, for either installed assistant."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.tests._support.second_assistant import HELPER, second_assistant
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http._confirming_assistant import (
    CONFIRM_CALL_ID,
    CONFIRM_TOOL,
    build_confirming_spec,
)
from pathfinder.tests.integration.http.conftest import bearer_client_for

UNAUTHORIZED = 401


async def turn(
    app: FastAPI,
    user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    *,
    conversation_id: UUID,
    prompt: str,
    assistant_id: str | None = None,
) -> list[dict[str, Any]]:
    """Drive one turn end to end and return its streamed chunks."""
    body = chat_post_body(conversation_id, prompt)
    if assistant_id is not None:
        body["assistantId"] = assistant_id
    return await turn_with_body(app, user_id, in_memory_jobs, body=body)


async def turn_with_body(
    app: FastAPI,
    user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    *,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    queued = len(chat_turn_jobs(in_memory_jobs))
    async with bearer_client_for(app, user_id) as client:
        post = asyncio.create_task(
            client.post("/api/v1/chat", json=body, timeout=60.0),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(in_memory_jobs, queued),
            timeout=10.0,
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=60.0)
    assert response.status_code == 200, response.text
    return parse_sse_body(response.text)


async def assistant_of(
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


def text_of(chunks: list[dict[str, Any]]) -> str:
    return "".join(c.get("delta", "") for c in chunks if c["type"] == "text-delta")


@pytest.fixture
def confirming_assistant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Serve the second assistant's id from one whose one tool needs approval."""
    with second_assistant(monkeypatch, build_confirming_spec):
        yield


def approval_body(
    conversation_id: UUID,
    *,
    approved: bool,
    reason: str | None = None,
) -> dict[str, Any]:
    """The body the client sends when the user answers an approval card."""
    approval: dict[str, Any] = {
        "id": CONFIRM_CALL_ID,
        "approved": approved,
    }
    if reason is not None:
        approval["reason"] = reason
    message_id = str(uuid4())
    return {
        "trigger": "submit-message",
        "id": message_id,
        "messages": [
            {
                "id": message_id,
                "role": "assistant",
                "parts": [
                    {
                        "type": f"tool-{CONFIRM_TOOL}",
                        "toolCallId": CONFIRM_CALL_ID,
                        "state": "approval-responded",
                        "input": {"geneSetId": "kinase-candidates"},
                        "approval": approval,
                    },
                ],
            },
        ],
        "conversationId": str(conversation_id),
        "siteId": "plasmodb",
        "assistantId": HELPER,
    }
