"""A one-agent assistant's approval card, answered over the chat route."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.tests.integration.http._confirming_assistant import (
    CONFIRM_CALL_ID,
    CONFIRM_PROMPT,
    CONFIRMED_REPLY,
)
from pathfinder.tests.integration.http._two_assistants import (
    SITE_HELP,
    approval_body,
    confirming_assistant,
    text_of,
    turn,
    turn_with_body,
)
from pathfinder.tests.integration.http.conftest import make_user

__all__ = ["confirming_assistant"]


async def test_a_one_agent_assistant_asks_the_user_before_it_runs_the_tool(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    confirming_assistant: None,
) -> None:
    del patch_app_db_engine, confirming_assistant
    owner = await make_user(db_session)

    chunks = await turn(
        app,
        owner.id,
        in_memory_jobs,
        conversation_id=uuid4(),
        prompt=CONFIRM_PROMPT,
        assistant_id=SITE_HELP,
    )

    types = [c["type"] for c in chunks]
    requests = [c for c in chunks if c["type"] == "tool-approval-request"]
    assert [c["toolCallId"] for c in requests] == [CONFIRM_CALL_ID]
    assert "error" not in types
    assert types[-2:] == ["finish", "done"]


async def test_the_answered_card_runs_the_tool_on_the_next_request(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    confirming_assistant: None,
) -> None:
    del patch_app_db_engine, confirming_assistant
    owner = await make_user(db_session)
    conversation_id = uuid4()
    await turn(
        app,
        owner.id,
        in_memory_jobs,
        conversation_id=conversation_id,
        prompt=CONFIRM_PROMPT,
        assistant_id=SITE_HELP,
    )

    chunks = await turn_with_body(
        app,
        owner.id,
        in_memory_jobs,
        body=approval_body(conversation_id, approved=True),
    )

    outputs = [c for c in chunks if c["type"] == "tool-output-available"]
    assert [c["toolCallId"] for c in outputs] == [CONFIRM_CALL_ID]
    assert text_of(chunks) == CONFIRMED_REPLY


async def test_a_refused_card_denies_the_call_over_the_same_route(
    app: FastAPI,
    patch_app_db_engine: None,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    confirming_assistant: None,
) -> None:
    del patch_app_db_engine, confirming_assistant
    owner = await make_user(db_session)
    conversation_id = uuid4()
    await turn(
        app,
        owner.id,
        in_memory_jobs,
        conversation_id=conversation_id,
        prompt=CONFIRM_PROMPT,
        assistant_id=SITE_HELP,
    )

    chunks = await turn_with_body(
        app,
        owner.id,
        in_memory_jobs,
        body=approval_body(conversation_id, approved=False, reason="no thanks"),
    )

    denials = [c for c in chunks if c["type"] == "tool-output-denied"]
    assert [c["toolCallId"] for c in denials] == [CONFIRM_CALL_ID]
    assert [c for c in chunks if c["type"] == "tool-output-available"] == []
