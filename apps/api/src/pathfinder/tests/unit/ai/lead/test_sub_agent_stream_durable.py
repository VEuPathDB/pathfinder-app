"""One sub-agent step can hand several calls to the worker.

The park records every durable call of the run, and the completion turn
resumes it with a result for each. A run that owes results for two tasks and
receives one keeps waiting instead of failing.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import DurableTaskResult
from assistant_core.tasks import decorator
from pydantic_ai import Agent, DeferredToolRequests, RunContext, Tool
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.toolsets import FunctionToolset
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph import _lead_model
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_turn import resolve_turn_resumption
from pathfinder.ai.graph.lead_node import _drive_lead_stream
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import sub_agent_stream, sub_agent_tools
from pathfinder.ai.lead.lead_agent import LEAD_MODEL, LeadAgent, LeadResponse
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import verify_strategy
from pathfinder.ai.tools.standalone.experiment import run_control_tests_on_step
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    called_tool_names,
    final_result_part,
    lead_runtime,
    pipeline_state,
    tool_script_model,
)

_TASK_A = UUID("0c6100d2-0000-4000-8000-00000000000a")
_TASK_B = UUID("0c6100d2-0000-4000-8000-00000000000b")
_CALL_A = "call_controls_a"
_CALL_B = "call_controls_b"
_CALL_PEEK = "call_peek"
_INSTRUCTIONS = "Call the tools the script names, then return the typed output."
_VERIFICATION_FINAL: dict[str, Any] = {
    "digest": {
        "disposition": "done",
        "prose": "both steps recovered their positive controls",
        "reason": "control tests returned",
        "success": True,
    },
}
_LEAD_FINAL: dict[str, Any] = {
    "prose": "scripted",
    "nextState": "await_user",
    "strategyChanged": False,
}
_RESULT_A: dict[str, Any] = {"positiveIntersection": 3, "positiveControlsCount": 3}
_RESULT_B: dict[str, Any] = {"positiveIntersection": 1, "positiveControlsCount": 2}

_PEEK_CALLS: list[int] = []


class _Deferred:
    """Records what the durable decorator handed the worker."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.jobs: list[dict[str, Any]] = []

    def configure_task(self, **kwargs: Any) -> _Deferred:
        self.jobs.append(kwargs)
        return self

    async def defer_async(self, **kwargs: Any) -> None:
        self.jobs[-1] = {**self.jobs[-1], **kwargs}


@pytest.fixture
def deferred(monkeypatch: pytest.MonkeyPatch) -> _Deferred:
    recorder = _Deferred()
    task_ids = iter((_TASK_A, _TASK_B))

    async def _create(**kwargs: Any) -> UUID:
        recorder.created.append(kwargs)
        return next(task_ids)

    monkeypatch.setattr(decorator, "create_background_task", _create)
    monkeypatch.setattr(decorator, "task_app", lambda: recorder)
    return recorder


@pytest.fixture
def writer(monkeypatch: pytest.MonkeyPatch) -> ChunkCollector:
    captured = ChunkCollector()
    monkeypatch.setattr(sub_agent_stream, "get_stream_writer", lambda: captured)
    monkeypatch.setattr(decorator, "get_stream_writer", lambda: captured)
    return captured


def _two_controls_and_a_peek() -> FunctionModel:
    """One step that tests two built steps and peeks at one of them."""

    def _parts(messages: list[ModelMessage]) -> list[ToolCallPart]:
        if called_tool_names(messages):
            return [final_result_part(_VERIFICATION_FINAL)]
        return [
            ToolCallPart(
                tool_name="run_control_tests_on_step",
                args={"wdk_step_id": 440230693},
                tool_call_id=_CALL_A,
            ),
            ToolCallPart(
                tool_name="run_control_tests_on_step",
                args={"wdk_step_id": 440230653},
                tool_call_id=_CALL_B,
            ),
            ToolCallPart(
                tool_name="peek_records",
                args={"wdk_step_id": 440230693},
                tool_call_id=_CALL_PEEK,
            ),
        ]

    return tool_script_model(_parts)


def _lead_calls_verify() -> FunctionModel:
    def _part(messages: list[ModelMessage]) -> ToolCallPart:
        if "verify_strategy" not in called_tool_names(messages):
            return ToolCallPart(
                tool_name="verify_strategy",
                args={"reason": "check both built steps"},
                tool_call_id="call_verify_strategy",
            )
        return final_result_part(_LEAD_FINAL)

    return tool_script_model(_part)


def _quota_offline() -> AsyncSession:
    msg = "no database in this unit test"
    raise OperationalError(msg, None, Exception(msg))


def _state() -> PipelineState:
    state = pipeline_state(
        user_prompt="Run control tests on both steps.",
        user_message_id=uuid4(),
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1", "s2"],
        failed_steps=[],
        root_count=132,
    )
    return state


def _deps(state: PipelineState) -> LeadDeps:
    return LeadDeps(
        state=state,
        intent=None,
        runtime=dataclasses.replace(lead_runtime(), db_session_factory=_quota_offline),
        retrieved_memories=[],
    )


def _lead_agent() -> LeadAgent:
    agent: LeadAgent = Agent(
        LEAD_MODEL,
        output_type=[LeadResponse, DeferredToolRequests],
        deps_type=LeadDeps,
        instructions=_INSTRUCTIONS,
        tools=[Tool(verify_strategy)],
        retries=3,
        name="lead",
        defer_model_check=True,
    )
    return agent


async def peek_records(ctx: RunContext[AgentDeps], wdk_step_id: int) -> str:
    """A non-durable sibling that settles inside the same model step."""
    del ctx
    _PEEK_CALLS.append(wdk_step_id)
    return f"10 sample records from step {wdk_step_id}"


@pytest.fixture(autouse=True)
def peek_calls() -> Iterator[list[int]]:
    _PEEK_CALLS.clear()
    yield _PEEK_CALLS
    _PEEK_CALLS.clear()


def _verification_toolset() -> FunctionToolset[AgentDeps]:
    return FunctionToolset[AgentDeps](
        tools=[
            Tool(run_control_tests_on_step, sequential=True, max_retries=3),
            Tool(peek_records),
        ],
    )


async def _drive(
    *,
    state: PipelineState,
    deps: LeadDeps,
    writer: ChunkCollector,
) -> _LeadRunCapture:
    capture = _LeadRunCapture()
    await _drive_lead_stream(
        state=state,
        agent=_lead_agent(),
        deps=deps,
        capture=capture,
        writer=writer,
        message_id=uuid4(),
    )
    return capture


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lead_model, "get_mock_model", _lead_calls_verify)
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", _two_controls_and_a_peek)


async def _park(
    *,
    monkeypatch: pytest.MonkeyPatch,
    state: PipelineState,
    writer: ChunkCollector,
) -> _LeadRunCapture:
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[_verification_toolset()],
        instructions=_INSTRUCTIONS,
    ):
        return await _drive(state=state, deps=_deps(state), writer=writer)


def _answered(parked: Any, first_task: UUID) -> PipelineState:
    resumed = _state()
    resumed.pending_durable_call = parked
    resumed.durable_result = DurableTaskResult(
        task_id=first_task,
        status="success",
        result=_RESULT_B if first_task is _TASK_B else _RESULT_A,
    )
    return resumed


@pytest.mark.usefixtures("scripted")
async def test_the_park_records_every_durable_call_of_the_run(
    writer: ChunkCollector,
    deferred: _Deferred,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = await _park(monkeypatch=monkeypatch, state=_state(), writer=writer)

    assert len(deferred.jobs) == 2
    parked = capture.pending_durable_call
    assert parked is not None
    assert [call.tool_call_id for call in parked.durable_calls] == [_CALL_A, _CALL_B]
    assert [call.task_id for call in parked.durable_calls] == [_TASK_A, _TASK_B]
    assert {call.durable_tool_name for call in parked.durable_calls} == {
        "run_control_tests_on_step",
    }
    started = writer.data_of("data-background-task-started")
    assert [c["taskId"] for c in started] == [str(_TASK_A), str(_TASK_B)]


@pytest.mark.usefixtures("scripted", "deferred")
async def test_one_result_of_two_leaves_the_run_parked(
    writer: ChunkCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = await _park(monkeypatch=monkeypatch, state=_state(), writer=writer)
    parked = capture.pending_durable_call
    assert parked is not None

    waiting = _answered(parked, _TASK_A)

    resumption = await resolve_turn_resumption(state=waiting, deps=_deps(waiting))

    assert resumption.results is None
    assert resumption.still_durable is parked


def _fully_answered(parked: Any) -> PipelineState:
    resumed = _answered(parked, _TASK_B)
    resumed.durable_results = [
        DurableTaskResult(task_id=_TASK_A, status="success", result=_RESULT_A),
        DurableTaskResult(task_id=_TASK_B, status="success", result=_RESULT_B),
    ]
    return resumed


@pytest.mark.usefixtures("scripted", "deferred")
async def test_the_last_result_resumes_the_run_with_every_answer(
    writer: ChunkCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = await _park(monkeypatch=monkeypatch, state=_state(), writer=writer)
    parked = capture.pending_durable_call
    assert parked is not None

    resumed = _fully_answered(parked)

    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[_verification_toolset()],
        instructions=_INSTRUCTIONS,
    ):
        second = await _drive(state=resumed, deps=_deps(resumed), writer=writer)

    assert second.pending_durable_call is None
    digest = resumed.domain.verification_digest
    assert digest is not None
    assert digest.prose == "both steps recovered their positive controls"
    # A durable tool's summary rides its result's metadata, which the dispatch
    # renders as the inner step's row rather than a chunk of its own.
    answered = [
        data
        for data in writer.data_of("data-sub-agent-step")
        if data["toolCallId"] in {_CALL_A, _CALL_B} and data["state"] == "completed"
    ]
    assert [row["toolCallId"] for row in answered] == [_CALL_A, _CALL_B]
    assert answered[0]["resultSummary"] == "3 of 3 positive controls recovered"
    assert answered[1]["resultSummary"] == "1 of 2 positive controls recovered"


@pytest.mark.usefixtures("scripted")
async def test_the_completion_turn_replays_nothing_the_parked_step_settled(
    writer: ChunkCollector,
    deferred: _Deferred,
    peek_calls: list[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture = await _park(monkeypatch=monkeypatch, state=_state(), writer=writer)
    parked = capture.pending_durable_call
    assert parked is not None
    assert peek_calls == [440230693]
    assert len(deferred.jobs) == 2

    resumed = _fully_answered(parked)

    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[_verification_toolset()],
        instructions=_INSTRUCTIONS,
    ):
        await _drive(state=resumed, deps=_deps(resumed), writer=writer)

    assert peek_calls == [440230693]
    assert len(deferred.jobs) == 2
