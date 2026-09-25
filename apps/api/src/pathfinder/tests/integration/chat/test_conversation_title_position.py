"""The thread title lands at one defined point of every turn.

The title comes from a task of its own, so these runs vary what that task
costs and read the last chunks of the turn.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.ai.conversation import turn_runner
from pathfinder.tests.integration.chat._helpers import run_one_chat_turn

_PROMPT = "hi"
_TITLE = "Deterministic Thread Title"


@dataclass
class _TitleTask:
    """A stand-in title model that reports whether the runner cancelled it."""

    delay_seconds: float
    cancelled: bool = False

    async def __call__(self, *args: object, **kwargs: object) -> str:
        del args, kwargs
        try:
            await asyncio.sleep(self.delay_seconds)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return _TITLE


@pytest.fixture
async def chat_stack(
    patch_app_db_engine: None,
    db_cleaner: None,
    signed_in_to_veupathdb: None,
) -> None:
    """Hold the database, the clean tables and the WDK identity for one turn."""
    del patch_app_db_engine, db_cleaner, signed_in_to_veupathdb


@pytest.mark.parametrize("delay_seconds", [0.0, 0.4])
async def test_the_title_is_the_last_chunk_before_finish(
    app: FastAPI,
    chat_stack: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    delay_seconds: float,
) -> None:
    """A title ready early and a title ready late take the same position."""
    del chat_stack
    title = _TitleTask(delay_seconds=delay_seconds)
    monkeypatch.setattr(turn_runner, "charged_conversation_title", title)

    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_PROMPT,
    )

    types = [str(chunk.get("type")) for chunk in chunks]
    title_positions = [
        index for index, kind in enumerate(types) if kind == "data-conversation-title"
    ]
    assert title_positions == [len(types) - 3], types
    assert types[-3:] == ["data-conversation-title", "finish", "done"]
    assert chunks[-3]["data"] == {"title": _TITLE}
    assert title.cancelled is False


@pytest.mark.parametrize("ceiling_seconds", [0.05, 0.5])
async def test_a_title_past_its_wait_leaves_the_turn_alone(
    app: FastAPI,
    chat_stack: None,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    ceiling_seconds: float,
) -> None:
    """The runner waits the ceiling, cancels the title task and finishes."""
    del chat_stack
    title = _TitleTask(delay_seconds=600.0)
    monkeypatch.setattr(turn_runner, "_TITLE_WAIT_SECONDS", ceiling_seconds)
    monkeypatch.setattr(turn_runner, "charged_conversation_title", title)

    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=_PROMPT,
    )

    types = [str(chunk.get("type")) for chunk in chunks]
    assert "data-conversation-title" not in types
    assert types[-2:] == ["finish", "done"]
    assert chunks[-2]["finishReason"] == "stop"
    assert title.cancelled is True
