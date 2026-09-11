"""The debugger defers a chat turn under the same per-conversation lock."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.devtools import chat
from pathfinder.jobs.payloads import ChatTurnPayload


class _FakeDeferrer:
    def __init__(self, recorder: dict[str, Any]) -> None:
        self._recorder = recorder

    async def defer_async(self, **kwargs: Any) -> int:
        self._recorder["deferred"] = kwargs
        return 1


class _FakeJob:
    def __init__(self) -> None:
        self.recorder: dict[str, Any] = {}

    def configure(self, **options: Any) -> _FakeDeferrer:
        self.recorder["options"] = options
        return _FakeDeferrer(self.recorder)


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


async def test_the_defer_carries_the_conversation_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _FakeJob()
    monkeypatch.setattr(chat, "procrastinate_app", _FakeApp())
    monkeypatch.setattr(chat, "run_chat_turn_job", job)
    conversation_id = uuid4()

    await chat._defer_chat_turn(_payload(conversation_id))

    assert job.recorder["options"] == {"lock": str(conversation_id)}
    deferred = job.recorder["deferred"]
    assert deferred["payload"]["body"]["conversationId"] == str(conversation_id)
