from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.errors import ModelDeclinedError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaToolCall,
    DeltaToolCalls,
    FunctionModel,
)

from pathfinder.ai.graph import _lead_model, _lead_reading
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests._support.scripted_reading import read_as
from pathfinder.tests.unit.ai.graph._approval_turn import Collector
from pathfinder.tests.unit.ai.graph.test_lead_turn_budget import _deps, _state

_DECLINED = ModelDeclinedError("The model declined this request.", model_id="m")


class _FirstRequest:
    def __init__(self) -> None:
        self.tools: list[str] = []
        self.classification: list[IntentClassification | None] = []

    def model(self, deps: LeadDeps) -> FunctionModel:
        def _part(info: AgentInfo) -> ToolCallPart:
            self.tools = [tool.name for tool in info.function_tools]
            intent = deps.intent
            self.classification.append(
                None if intent is None else intent.classification
            )
            return ToolCallPart(
                tool_name="final_result",
                args={"prose": "answered", "nextState": "await_user"},
                tool_call_id="call_final",
            )

        def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            del messages
            return ModelResponse(parts=[_part(info)])

        async def _stream(
            messages: list[ModelMessage], info: AgentInfo
        ) -> AsyncIterator[DeltaToolCalls]:
            del messages
            part = _part(info)
            yield {
                0: DeltaToolCall(
                    name=part.tool_name,
                    json_args=part.args_as_json_str(),
                    tool_call_id=part.tool_call_id,
                )
            }

        return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


def test_the_lead_s_first_request_holds_the_reading_and_no_classify_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_as(monkeypatch, "follow_up_question")
    state = _state()
    deps = _deps(state)
    first = _FirstRequest()
    model = first.model(deps)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: model)
    writer: Any = Collector()

    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=deps,
            capture=_LeadRunCapture(),
            writer=writer,
            message_id=uuid4(),
        )
    )

    assert first.classification == [IntentClassification.FOLLOW_UP_QUESTION]
    assert "classify_user_intent" not in first.tools
    assert "read_ledger_section" in first.tools
    assert deps.state.turn_markers.intent_classified is True


def test_a_reading_the_provider_declines_withdraws_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _declined(state: PipelineState, words: str) -> UserIntent:
        del state, words
        raise _DECLINED

    monkeypatch.setattr(_lead_reading, "scripted_intent", _declined)
    state = _state()
    deps = _deps(state)
    first = _FirstRequest()
    model = first.model(deps)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: model)
    capture = _LeadRunCapture()
    writer = Collector()
    emitted: Any = writer

    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=deps,
            capture=capture,
            writer=emitted,
            message_id=uuid4(),
        )
    )

    assert (first.classification, capture.declined is not None) == ([], True)
