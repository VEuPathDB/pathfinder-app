"""A turn that asks for no strategy leaves none behind.

Two messages through the real dispatcher on the deterministic provider: a
request to remember a preference, and a bare statement of what the user works
on. Neither may reach a sub-agent or a strategy snapshot.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.ai.lead.card_contract import CARD_TOOLS
from pathfinder.tests.integration.chat._helpers import run_one_chat_turn

_REMEMBER_PROMPT = (
    "Please remember for future sessions: I always work with P. falciparum 3D7. "
    "[[arc:remember]]"
)
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


async def test_a_remember_request_stores_and_builds_nothing(
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
        prompt=_REMEMBER_PROMPT,
    )

    assert "remember" in _tool_names(chunks)
    assert "frame_problem" not in _tool_names(chunks)
    assert "data-graph-snapshot" not in _types(chunks)


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
    assert text == _CONTEXT_REPLY
