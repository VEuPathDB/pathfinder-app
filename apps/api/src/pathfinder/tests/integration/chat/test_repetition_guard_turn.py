"""A PathFinder turn that repeats one catalog read is stopped by the guard.

The scripted FRAME arc asks for the same listing on every step. The guard
refuses the third identical call and ends the sub-agent's pass on the fourth,
so the turn finishes with a reply instead of spending its whole budget.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from assistant_core.capabilities.repetition_guard import (
    DEFAULT_REPETITION_THRESHOLD,
    REPETITION_MARKER,
)
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.tests._support.recorded_searches import serve_recorded_listing
from pathfinder.tests.integration.chat._helpers import run_one_chat_turn

_PROMPT = "read the catalog again and again [[arc:frame-loop]]"
_LOOPING_TOOL = "list_searches"


@pytest.fixture(autouse=True)
def recorded_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded_listing(monkeypatch)


def _inner_steps(chunks: list[dict[str, Any]], tool: str) -> list[dict[str, Any]]:
    return [
        chunk["data"]
        for chunk in chunks
        if chunk["type"] == "data-sub-agent-step"
        and chunk["data"].get("toolName") == tool
    ]


async def test_the_repeated_catalog_read_is_refused_inside_frame(
    app: FastAPI,
    patch_app_db_engine: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb

    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_PROMPT,
    )

    refused = [
        step
        for step in _inner_steps(chunks, _LOOPING_TOOL)
        if REPETITION_MARKER in (step.get("resultSummary") or "")
    ]
    assert refused
    assert refused[0]["state"] == "completed"


async def test_the_loop_stops_rather_than_spending_the_phase_budget(
    app: FastAPI,
    patch_app_db_engine: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb

    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_PROMPT,
    )

    started = [
        step
        for step in _inner_steps(chunks, _LOOPING_TOOL)
        if step["state"] == "started"
    ]
    assert len(started) == DEFAULT_REPETITION_THRESHOLD + 1


async def test_the_stopped_turn_still_answers_the_user(
    app: FastAPI,
    patch_app_db_engine: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    signed_in_to_veupathdb: None,
) -> None:
    del patch_app_db_engine, signed_in_to_veupathdb

    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_PROMPT,
    )

    types = [chunk["type"] for chunk in chunks]
    text = "".join(c.get("delta", "") for c in chunks if c["type"] == "text-delta")
    assert "error" not in types
    assert types[-2:] == ["finish", "done"]
    assert text
