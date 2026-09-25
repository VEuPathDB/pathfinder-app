"""The Lead's run starts from the whole user message: the attached image, then
the text, so the model that reads the message reads the file."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import BinaryImage
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart, TextUIPart

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.tests.unit.ai.graph._approval_turn import Collector, scripted_model
from pathfinder.tests.unit.ai.lead.conftest import lead_deps

_TEXT = "which genes are in this image?"
_PNG_URL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4"
    "nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_message_id=uuid4(),
        user_prompt=_TEXT,
        user_parts=[
            FileUIPart(media_type="image/png", filename="table.png", url=_PNG_URL),
            TextUIPart(text=_TEXT, state="done"),
        ],
    )


def _first_request_content(monkeypatch: pytest.MonkeyPatch) -> Any:
    seen: list[list[ModelMessage]] = []

    def _answer(messages: list[ModelMessage]) -> ToolCallPart:
        seen.append(list(messages))
        return ToolCallPart(
            tool_name="final_result",
            args={"prose": "read", "nextState": "await_user", "strategyChanged": False},
            tool_call_id="call_final",
        )

    model = scripted_model(_answer)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: model)
    state = _state()
    emitted: Any = Collector()
    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=lead_deps(state),
            capture=_LeadRunCapture(),
            writer=emitted,
            message_id=uuid4(),
        ),
    )
    first = seen[0][-1]
    assert isinstance(first, ModelRequest)
    prompts = [p for p in first.parts if isinstance(p, UserPromptPart)]
    assert len(prompts) == 1
    return prompts[0].content


def test_the_first_request_holds_the_image_then_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = _first_request_content(monkeypatch)

    assert [type(c) for c in content] == [BinaryImage, str]
    assert content[0].media_type == "image/png"
    assert content[1] == _TEXT
