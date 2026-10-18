"""A turn that ends on an approval card suspends, so its message stays open."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from pathfinder.ai.conversation import turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody

_CALL = "call_adopt"


@dataclass
class _Writer:
    conversation_id: UUID = field(default_factory=uuid4)
    turn_id: UUID = field(default_factory=uuid4)
    chunks: list[dict[str, Any]] = field(default_factory=list)

    async def write(self, chunk: dict[str, Any]) -> int:
        self.chunks.append(chunk)
        return len(self.chunks)


@dataclass
class _RuntimeCtx:
    cancel_event: asyncio.Event


@dataclass
class _Graph:
    chunks: list[dict[str, Any]]

    def astream(
        self,
        graph_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
        stream_mode: str,
    ) -> AsyncIterator[Any]:
        del graph_input, config, context, stream_mode
        return self._iter()

    async def _iter(self) -> AsyncIterator[Any]:
        for chunk in self.chunks:
            yield {"chunk": chunk}


def _body(conversation_id: UUID) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "id": str(conversation_id),
            "trigger": "submit-message",
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "separate these"}],
                },
            ],
            "conversationId": str(conversation_id),
            "siteId": "plasmodb",
        },
    )


@pytest.fixture(autouse=True)
def _no_cancel_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_poll(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(turn_runner, "watch_for_cancel", _no_poll)


async def _drive(chunks: list[dict[str, Any]]) -> turn_runner._DriveResult:
    writer = _Writer()
    return await turn_runner._drive_graph(
        body=_body(writer.conversation_id),
        graph_input={"turn_message_id": writer.turn_id, "user_id": uuid4()},
        compiled_graph=_Graph(chunks),
        runtime_context=_RuntimeCtx(cancel_event=asyncio.Event()),
        writer=writer,
    )


_ANNOUNCED = {
    "type": "tool-input-available",
    "toolCallId": _CALL,
    "toolName": "adopt_separating_strategy",
    "input": {"task_id": "t1"},
}


async def test_a_turn_that_ends_on_an_approval_request_suspends() -> None:
    result = await _drive(
        [
            _ANNOUNCED,
            {"type": "tool-approval-request", "approvalId": _CALL, "toolCallId": _CALL},
        ],
    )

    assert result.suspended is True


async def test_a_turn_with_no_approval_request_runs_to_completion() -> None:
    result = await _drive(
        [
            _ANNOUNCED,
            {"type": "tool-output-available", "toolCallId": _CALL, "output": {}},
        ],
    )

    assert result.suspended is False
