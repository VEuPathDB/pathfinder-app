"""The debugger defers a chat turn the way the chat route does."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import JsonValue
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.devtools import chat
from pathfinder.jobs.payloads import ChatTurnPayload


class _FakeAppCtx:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeApp:
    def open_async(self) -> _FakeAppCtx:
        return _FakeAppCtx()


def _payload(conversation_id: UUID) -> ChatTurnPayload:
    message_id = str(uuid4())
    return ChatTurnPayload(
        body=ChatRequestBody(
            id=message_id,
            messages=[
                UIMessage(id=message_id, role="user", parts=[TextUIPart(text="hi")]),
            ],
            conversation_id=conversation_id,
            site_id="plasmodb",
        ),
        user_id=uuid4(),
        turn_id=uuid4(),
        assistant_id="pathfinder",
    )


async def test_the_defer_names_the_thread_the_turn_belongs_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runtime locks on the thread, so the id it is handed is the turn's."""
    recorded: dict[str, Any] = {}

    async def defer(*, conversation_id: UUID, payload: Mapping[str, JsonValue]) -> int:
        recorded["conversation_id"] = conversation_id
        recorded["payload"] = payload
        return 1

    monkeypatch.setattr(chat, "procrastinate_app", _FakeApp())
    monkeypatch.setattr(chat, "defer_chat_turn", defer)
    conversation_id = uuid4()

    await chat._defer_chat_turn(_payload(conversation_id))

    assert recorded["conversation_id"] == conversation_id
    assert recorded["payload"]["body"]["conversationId"] == str(conversation_id)
