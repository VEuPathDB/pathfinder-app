"""The Lead's run reads the turn's site and message from the scripted scope."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.models.scripted import current_scope_id, current_user_text
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests.unit.ai.graph._approval_turn import Collector

_PROMPT = "Which genes are upregulated after a blood meal? [[arc:echo]]"
_ANSWER = {"prose": "Read.", "nextState": "await_user", "strategyChanged": False}


def _no_database() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _recording(seen: list[tuple[str, str]]) -> FunctionModel:
    def _answer() -> ToolCallPart:
        seen.append((current_scope_id.get(), current_user_text.get()))
        return ToolCallPart("final_result", _ANSWER)

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[_answer()])

    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[dict[int, DeltaToolCall]]:
        del messages, info
        part = _answer()
        yield {0: DeltaToolCall(name=part.tool_name, json_args=part.args_as_json_str())}

    return FunctionModel(_fn, stream_function=_stream, model_name="recording")


async def _turn(site_id: str, seen: list[tuple[str, str]]) -> None:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id=site_id,
        mode="strategy",
        user_prompt=_PROMPT,
        user_message_id=uuid4(),
    )
    deps = LeadDeps(
        state=state,
        intent=None,
        runtime=Context(
            site_id=site_id,
            user_id=state.user_id,
            strategy_session=StrategySession(site_id=site_id),
            db_session_factory=_no_database,
            cancel_event=asyncio.Event(),
        ),
        retrieved_memories=[],
    )
    writer: Any = Collector()
    await _drive_lead_stream(
        state=state,
        agent=build_lead_agent(),
        deps=deps,
        capture=_LeadRunCapture(),
        writer=writer,
        message_id=uuid4(),
    )


def test_the_lead_run_reads_the_turn_site_and_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: _recording(seen))

    asyncio.run(_turn("vectorbase", seen))

    assert seen[0] == ("vectorbase", _PROMPT)


def test_binding_the_scope_sets_both_values() -> None:
    async def _bound() -> tuple[str, str]:
        bind_scripted_scope("toxodb", "Find ME49 kinases")
        return current_scope_id.get(), current_user_text.get()

    assert asyncio.run(_bound()) == ("toxodb", "Find ME49 kinases")
