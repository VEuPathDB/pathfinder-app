"""A message typed past a card the Lead raised declines the card; a typed yes runs it.

The whole PathFinder assistant over the real chat route, the real turn graph
and the checkpoint. Only the model is a double: it raises one card, then
answers whatever reaches it next.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

from pathfinder.ai.graph import _lead_model
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.unit.ai.graph._approval_turn import (
    CARD_REPLY,
    LEAD_FINAL,
    scripted_model,
    tool_calls,
)

CALL_ID = "call_card"
ASK = "Start the kinase strategy over."
TYPED = "Actually, keep the strategy and add a GO filter."
DECLINED_BY_REPLY = "The researcher sent a new message instead of answering the card."
_TIMEOUT_SECONDS = 120.0
_CLASSIFY = {
    "intent": {"classification": "edit_strategy", "inferredGoal": "change it"},
}
_WITH_THE_STACK = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb"
)
CLEAR: tuple[str, dict[str, Any]] = (
    "clear_strategy",
    {"confirm": True, "reply": CARD_REPLY},
)
CARDS: list[tuple[str, dict[str, Any]]] = [
    CLEAR,
    (
        "consult_user",
        {"questions": [{"id": "q1", "prompt": "Which strain?"}], "reply": CARD_REPLY},
    ),
]


def _reads(messages: list[ModelMessage]) -> list[tuple[str, Any]]:
    """The card's returns and the prompts one model call read."""
    return [
        ("return", part.content)
        if isinstance(part, ToolReturnPart)
        else ("prompt", part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if (isinstance(part, ToolReturnPart) and part.tool_call_id == CALL_ID)
        or (isinstance(part, UserPromptPart) and part.content == TYPED)
    ]


def _card_lead(
    tool_name: str, args: dict[str, Any], seen: list[list[tuple[str, Any]]]
) -> FunctionModel:
    """Classify, raise the card, then answer."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        seen.append(_reads(messages))
        called = {c.tool_name for c in tool_calls(messages)}
        if "classify_user_intent" not in called:
            return ToolCallPart(
                tool_name="classify_user_intent",
                args=_CLASSIFY,
                tool_call_id="call_classify",
            )
        if tool_name not in called:
            return ToolCallPart(tool_name=tool_name, args=args, tool_call_id=CALL_ID)
        return ToolCallPart(
            tool_name="final_result",
            args=LEAD_FINAL,
            tool_call_id=f"call_final_{uuid4().hex[:8]}",
        )

    return scripted_model(_part)


async def _turn(
    app: FastAPI,
    user_id: UUID,
    jobs: InMemoryConnector,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    queued = len(chat_turn_jobs(jobs))
    async with client_for(app, user_id) as client:
        post = asyncio.create_task(
            client.post("/api/v1/chat", json=body, timeout=_TIMEOUT_SECONDS),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(jobs, queued),
            timeout=_TIMEOUT_SECONDS,
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=_TIMEOUT_SECONDS)
    assert response.status_code == 200, response.text
    return parse_sse_body(response.text)


def _call_ids(chunks: list[dict[str, Any]], chunk_type: str) -> list[str]:
    return [str(c["toolCallId"]) for c in chunks if c["type"] == chunk_type]


@_WITH_THE_STACK
@pytest.mark.parametrize("card", CARDS, ids=[name for name, _ in CARDS])
async def test_a_typed_message_declines_the_card_and_reaches_the_lead(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    card: tuple[str, dict[str, Any]],
) -> None:
    seen: list[list[tuple[str, Any]]] = []
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: _card_lead(*card, seen))
    conversation_id = uuid4()
    asked = await _turn(
        app, authed_user_id, in_memory_jobs, chat_post_body(conversation_id, ASK)
    )
    calls_before = len(seen)

    typed = await _turn(
        app, authed_user_id, in_memory_jobs, chat_post_body(conversation_id, TYPED)
    )

    assert _call_ids(asked, "tool-approval-request") == [CALL_ID]
    assert _call_ids(typed, "tool-approval-request") == []
    assert _call_ids(typed, "tool-output-denied") == [CALL_ID]
    assert seen[calls_before:] == [[("return", DECLINED_BY_REPLY), ("prompt", TYPED)]]


@_WITH_THE_STACK
async def test_a_typed_yes_runs_the_card_before_any_classification(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[tuple[str, Any]]] = []
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: _card_lead(*CLEAR, seen))
    conversation_id = uuid4()
    await _turn(
        app, authed_user_id, in_memory_jobs, chat_post_body(conversation_id, ASK)
    )

    typed = await _turn(
        app,
        authed_user_id,
        in_memory_jobs,
        chat_post_body(conversation_id, "Yes, go ahead."),
    )

    assert _call_ids(typed, "tool-input-error") == []
    assert CALL_ID in _call_ids(typed, "tool-output-available")
    assert "data-graph-cleared" in [c["type"] for c in typed]
