"""A turn that asks for no strategy leaves none behind.

Two messages through the real dispatcher on the deterministic provider: a
request to remember a preference, and a bare statement of what the user works
on. Neither may reach a sub-agent or a strategy snapshot.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.ai.lead.card_contract import CARD_TOOLS
from pathfinder.tests._support.qa_recording import needs_suite_recordings
from pathfinder.tests._support.read_text import as_read
from pathfinder.tests.integration.chat._helpers import run_one_chat_turn
from pathfinder.tests.integration.http.conftest import client_for

_STATED = "Please remember for future sessions: I always work with P. falciparum 3D7."
_REMEMBER_PROMPT = f"{_STATED} [[arc:remember]]"
_CONTEXT_PROMPT = (
    "I'm investigating virulence factors in Leishmania major [[arc:context]]"
)
_CONTEXT_REPLY = (
    "Good area to be in. I have not built anything yet. Say the word and I "
    "will put a candidate strategy together for it."
)


def _tool_names(chunks: list[dict[str, Any]]) -> list[str]:
    return [
        str(chunk["toolName"])
        for chunk in chunks
        if chunk.get("type") == "tool-input-available"
    ]


def _types(chunks: list[dict[str, Any]]) -> list[str]:
    return [str(chunk.get("type")) for chunk in chunks]


@pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb", "app_memory_store"
)
async def test_a_remember_request_stores_and_builds_nothing(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
) -> None:
    conversation_id = uuid4()
    asked = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_REMEMBER_PROMPT,
        conversation_id=conversation_id,
    )
    stored = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt="Yes, go ahead.",
        conversation_id=conversation_id,
    )
    chunks = asked + stored

    assert "tool-approval-request" in _types(asked)
    assert "tool-output-available" in _types(stored)
    assert "remember" in _tool_names(chunks)
    assert "frame_problem" not in _tool_names(chunks)
    assert "data-graph-snapshot" not in _types(chunks)
    async with client_for(app, authed_user_id) as client:
        memories = (await client.get("/api/v1/memories")).json()
    assert [item["value"]["summary"] for item in memories["preferences"]] == [_STATED]


@needs_suite_recordings
async def test_a_context_statement_answers_in_prose(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_CONTEXT_PROMPT,
    )

    assert "data-sub-agent-call" not in _types(chunks)
    assert "data-graph-snapshot" not in _types(chunks)
    assert CARD_TOOLS.isdisjoint(_tool_names(chunks))
    text = "".join(
        str(chunk.get("delta", ""))
        for chunk in chunks
        if chunk.get("type") == "text-delta"
    )
    assert as_read(text) == _CONTEXT_REPLY
