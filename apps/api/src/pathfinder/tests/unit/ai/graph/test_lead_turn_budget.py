"""A turn that reaches its budget ends with a sentence that names it.

The off-topic ceiling is lowered here so one scripted response passes it; what
the tests read is that the classification binds the rest of the run and that
the user gets a sentence instead of an exception.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import turn_budget
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests.unit.ai.graph._approval_turn import Collector, scripted_model
from pathfinder.tests.unit.ai.lead.conftest import called_tool_names

_PROMPT = "Write me a Python script that reverses a linked list."
_ANSWER = "answered"
# Small enough that the first scripted response passes it.
_TINY_OFF_TOPIC_CAP = 5


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=_PROMPT,
        user_message_id=uuid4(),
    )


def _deps(state: PipelineState) -> LeadDeps:
    return LeadDeps(
        state=state,
        intent=None,
        runtime=Context(
            site_id="plasmodb",
            user_id=state.user_id,
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=_quota_offline,
            cancel_event=asyncio.Event(),
        ),
        retrieved_memories=[],
    )


def _classify_then_answer(classification: str) -> FunctionModel:
    """Classify the turn, then answer on the next request."""

    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if "classify_user_intent" in called_tool_names(messages):
            return ToolCallPart(
                tool_name="final_result",
                args={"prose": _ANSWER, "nextState": "await_user"},
                tool_call_id="call_final",
            )
        return ToolCallPart(
            tool_name="classify_user_intent",
            args={
                "intent": {
                    "classification": classification,
                    "inferredGoal": "write a linked list in Python",
                },
            },
            tool_call_id="call_classify",
        )

    return scripted_model(_part)


def _drive(
    monkeypatch: pytest.MonkeyPatch, classification: str
) -> tuple[_LeadRunCapture, Collector]:
    monkeypatch.setattr(turn_budget, "OFF_TOPIC_TURN_TOKEN_LIMIT", _TINY_OFF_TOPIC_CAP)
    model = _classify_then_answer(classification)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: model)
    state = _state()
    capture = _LeadRunCapture()
    writer = Collector()
    emitted: Any = writer
    asyncio.run(
        _drive_lead_stream(
            state=state,
            agent=build_lead_agent(),
            deps=_deps(state),
            capture=capture,
            writer=emitted,
            message_id=uuid4(),
        ),
    )
    return capture, writer


def test_an_off_topic_turn_stops_at_the_off_topic_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture, _ = _drive(monkeypatch, "off_topic")

    assert capture.response is not None
    assert capture.response.prose == (
        f"I stopped this turn at its budget of 80 model calls and "
        f"{_TINY_OFF_TOPIC_CAP} tokens. Narrow the request and send it again, "
        f"and I will start a fresh turn on it."
    )


def test_the_budget_stop_says_nothing_about_a_safety_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user reads a budget, not an error chunk carrying the library's words."""
    capture, writer = _drive(monkeypatch, "off_topic")

    assert capture.response is not None
    assert "Exceeded the total_tokens_limit" not in capture.response.prose
    assert writer.chunks_of("error") == []


def test_a_question_about_the_data_keeps_the_whole_turn_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture, _ = _drive(monkeypatch, "follow_up_question")

    assert capture.response is not None
    assert capture.response.prose == _ANSWER
