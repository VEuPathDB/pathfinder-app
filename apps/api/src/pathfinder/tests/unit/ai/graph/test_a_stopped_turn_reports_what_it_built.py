"""A turn that stops after a build still says the strategy changed.

Every tool writes its markers through ``deps.state``, which the pre-turn hook
makes a copy of, so a reply that reads the pre-copy state reports nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database
from pathfinder.tests.unit.ai.graph._approval_turn import Collector


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find A. gambiae midgut proteases",
        user_message_id=uuid4(),
    )


def _context(state: PipelineState) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=state.user_id,
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )


def _raising_model(error: Exception) -> FunctionModel:
    def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        raise error

    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str]:
        del messages, info
        for _ in ():
            yield ""
        raise error

    return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


async def _turn_that_built_then_raised(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> _LeadRunCapture:
    state = _state()
    working = await refresh_live_strategy_state(state, _context(state))
    deps = LeadDeps(
        state=working, intent=None, runtime=_context(state), retrieved_memories=[]
    )
    deps.state.record_build(BuildOutcome(pushed_step_ids=["step_a"], root_count=132))
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: _raising_model(error))
    capture = _LeadRunCapture()
    writer: Any = Collector()
    await _drive_lead_stream(
        state=state,
        agent=build_lead_agent(),
        deps=deps,
        capture=capture,
        writer=writer,
        message_id=uuid4(),
    )
    return capture


@pytest.mark.asyncio
async def test_a_turn_that_ran_out_of_budget_after_a_build_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = await _turn_that_built_then_raised(
        UsageLimitExceeded("the turn reached its budget"), monkeypatch
    )

    assert capture.response is not None
    assert capture.response.strategy_changed is True


@pytest.mark.asyncio
async def test_a_turn_that_failed_after_a_build_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = await _turn_that_built_then_raised(
        RuntimeError("Connection error."), monkeypatch
    )

    assert capture.response is None or capture.response.strategy_changed is True
