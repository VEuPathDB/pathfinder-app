"""What reaches the caller when the Lead's run raises.

The emitter answers an exception with an error chunk of its own, except a
langgraph control-flow signal, which it re-raises so the graph sees it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import uuid4

import pytest
from langgraph.errors import GraphBubbleUp
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.logs import logged_events
from pathfinder.tests.unit.ai.graph._approval_turn import Collector

_LEAD_NODE_LOGGER = "pathfinder.ai.graph.lead_node"


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


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


def _raising_model(error: Exception) -> FunctionModel:
    """A model whose every request fails the way ``error`` says."""

    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        raise error

    async def _stream(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del messages, info
        for _ in ():
            yield {}
        raise error

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


def _drive(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    capture: _LeadRunCapture,
    writer: Collector,
) -> None:
    model = _raising_model(error)
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: model)
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find A. gambiae midgut proteases",
        user_message_id=uuid4(),
    )
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


def _turn_failures(caplog: pytest.LogCaptureFixture) -> Sequence[str]:
    """The events the turn logged as a failure of its own."""
    return logged_events(caplog.records, logger=_LEAD_NODE_LOGGER)


def test_a_graph_control_signal_reaches_the_graph_unlogged(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """langgraph decides what a bubbled signal means, so the turn re-raises it.

    The turn logs nothing: a signal the graph reads is not a failure, and the
    stack it would render carries every local of the run.
    """
    capture = _LeadRunCapture()
    writer = Collector()

    with caplog.at_level(logging.ERROR), pytest.raises(GraphBubbleUp):
        _drive(monkeypatch, GraphBubbleUp(), capture, writer)

    assert _turn_failures(caplog) == []
    assert capture.response is None
    assert writer.chunks_of("error") == []


def test_any_other_failure_reaches_the_user_as_an_error_chunk(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The contrast: the emitter answers this one, so the turn ends without it.

    The turn logs nothing here either. Only the loop that writes the chunks
    reports through ``lead_node``, and it ran to the end.
    """
    capture = _LeadRunCapture()
    writer = Collector()

    with caplog.at_level(logging.ERROR):
        _drive(monkeypatch, RuntimeError("the model refused"), capture, writer)

    assert [chunk["type"] for chunk in writer.chunks_of("error")] == ["error"]
    assert _turn_failures(caplog) == []
