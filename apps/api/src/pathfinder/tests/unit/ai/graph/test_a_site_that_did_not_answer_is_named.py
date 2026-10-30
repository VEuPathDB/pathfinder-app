from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_stops import fallback_prose
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.site_failures import failed_read, refused, timed_out
from pathfinder.tests.unit.ai.graph._approval_turn import Collector


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _raising_model(error: Exception) -> FunctionModel:
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
    monkeypatch: pytest.MonkeyPatch, error: Exception, capture: _LeadRunCapture
) -> Collector:
    monkeypatch.setattr(_lead_model, "get_mock_model", lambda: _raising_model(error))
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find the orthologs of PF3D7_1133400",
        user_message_id=uuid4(),
    )
    deps = LeadDeps(
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
        ),
    )
    return writer


def test_a_timeout_to_orthomcl_in_the_run_names_orthomcl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _LeadRunCapture()
    failure = asyncio.run(failed_read("orthomcl", timed_out))

    writer = _drive(monkeypatch, failure, capture)

    assert [chunk["errorText"] for chunk in writer.chunks_of("error")] == [
        "OrthoMCL did not answer."
    ]
    assert fallback_prose(capture, None, change="unchanged") == (
        "OrthoMCL did not answer, so I stopped this turn and nothing was changed. "
        "Send the message again and I will start over from it."
    )


def test_a_change_that_landed_before_the_site_failed_is_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _LeadRunCapture()

    _drive(monkeypatch, asyncio.run(failed_read("orthomcl", timed_out)), capture)

    assert fallback_prose(capture, None, change="unchecked") == (
        "OrthoMCL did not answer, so I stopped this turn. The change shown beside "
        "this reply landed and was not checked. Ask me to check it and I will go "
        "on from there."
    )


def test_a_refusal_in_the_run_keeps_its_own_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = _LeadRunCapture()
    failure = asyncio.run(failed_read("plasmodb", refused))

    writer = _drive(monkeypatch, failure, capture)

    assert [chunk["errorText"] for chunk in writer.chunks_of("error")] == [str(failure)]
    assert capture.unanswered_site is None
