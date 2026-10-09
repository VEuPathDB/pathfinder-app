from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from pathfinder.ai.conversation import turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.platform.tool_sources import metered_mcp_toolset


class _StopAtResolutionError(RuntimeError):
    pass


class _Writer:
    def __init__(self) -> None:
        self.conversation_id: UUID = uuid4()
        self.turn_id: UUID = uuid4()
        self.chunks: list[dict[str, Any]] = []

    async def write(self, chunk: dict[str, Any]) -> int:
        self.chunks.append(chunk)
        return len(self.chunks)


class _Spec:
    tool_sources: tuple[Any, ...] = ()


def _spec() -> Any:
    return _Spec()


async def _no_conversation(conversation_id: UUID) -> None:
    del conversation_id


async def test_the_turn_builds_each_source_through_the_metered_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builders: list[object] = []

    def resolved(**kwargs: Any) -> None:
        builders.append(kwargs["build_toolset"])
        raise _StopAtResolutionError

    monkeypatch.setattr(turn_runner, "load_conversation", _no_conversation)
    monkeypatch.setattr(turn_runner, "ResolvedToolSources", resolved)
    writer = _Writer()
    body = ChatRequestBody.model_validate(
        {
            "conversationId": str(writer.conversation_id),
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "hi"}],
                },
            ],
            "siteId": "plasmodb",
        },
    )

    with pytest.raises(_StopAtResolutionError):
        await turn_runner.run_turn(
            request=turn_runner.TurnRequest(body=body, user_id=uuid4()),
            spec=_spec(),
            compiled_graph=None,
            memory_store=None,
            writer=writer,
        )

    assert builders == [metered_mcp_toolset]
