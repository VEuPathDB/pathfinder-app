"""Two durable calls from one model step are answered by one completion turn.

One agent over the real turn graph, the real checkpointer, the real event
writer and the real runner. Only the model and the control-test wire are
doubles. The first task to finish opens no turn; the last one resumes the run
with an answer for every parked call.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.single_agent import single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.models.scripted import tool_return_parts
from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.spec import AssistantSpec
from fastapi import FastAPI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from procrastinate.testing import InMemoryConnector
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from sqlalchemy import select
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.experiment import run_control_tests_on_step
from pathfinder.assistants import registry
from pathfinder.assistants.pathfinder_spec import build_turn_context
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.assistants.site_help.spec import (
    SITE_HELP_ASSISTANT_ID,
    build_initial_state,
    charge_usage,
)
from pathfinder.jobs.impls import control_tests_impl, register_all_tools
from pathfinder.jobs.runner import run_durable_task
from pathfinder.persistence.models import BackgroundTask, User
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import WDK_AUTH_HEADER, client_for

_PROMPT = "run control tests on both steps and show me a few records"
_TOOL = "run_control_tests_on_step"
_DURABLE_TASK = f"durable:{_TOOL}"
_STEP_A = 440230693
_STEP_B = 440230653
_CALL_A = "call_controls_a"
_CALL_B = "call_controls_b"
_CALL_PEEK = "call_peek"
_POSITIVES = ["PF3D7_0102600"]


class _Resumed(BaseModel):
    """What the completion turn hands back to one parked tool call."""

    model_config = ConfigDict(extra="ignore")

    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


def _prose_for(control_returns: list[ToolReturnPart]) -> str:
    recovered: list[str] = []
    for part in control_returns:
        resumed = _Resumed.model_validate(part.content)
        step = (resumed.result or {}).get("stepId", "none")
        recovered.append(f"{step}:{resumed.status}")
    return f"Controls ran on {', '.join(recovered)}."


def _script(messages: list[ModelMessage]) -> list[TextPart | ToolCallPart]:
    """Test both steps and peek at one, then quote both recoveries."""
    control_returns = [
        part for part in tool_return_parts(messages) if part.tool_name == _TOOL
    ]
    if control_returns:
        return [TextPart(content=_prose_for(control_returns))]
    return [
        ToolCallPart(
            tool_name=_TOOL,
            args={"wdk_step_id": _STEP_A, "positive_controls": _POSITIVES},
            tool_call_id=_CALL_A,
        ),
        ToolCallPart(
            tool_name=_TOOL,
            args={"wdk_step_id": _STEP_B, "positive_controls": _POSITIVES},
            tool_call_id=_CALL_B,
        ),
        ToolCallPart(
            tool_name="peek_records",
            args={"wdk_step_id": _STEP_A},
            tool_call_id=_CALL_PEEK,
        ),
    ]


def _build_mock() -> FunctionModel:
    """A model whose one step makes three calls, then answers in prose."""

    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        return ModelResponse(parts=list(_script(messages)))

    async def _stream(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        del info
        parts = _script(messages)
        text = [part for part in parts if isinstance(part, TextPart)]
        if text:
            yield text[0].content
            return
        yield {
            index: DeltaToolCall(
                name=part.tool_name,
                json_args=part.args_as_json_str(),
                tool_call_id=part.tool_call_id,
            )
            for index, part in enumerate(parts)
            if isinstance(part, ToolCallPart)
        }

    return FunctionModel(_respond, stream_function=_stream, model_name="scripted")


async def peek_records(ctx: RunContext[AgentDeps], wdk_step_id: int) -> str:
    """A non-durable sibling that settles inside the same model step."""
    del ctx
    return f"10 sample records from step {wdk_step_id}"


def _build_agent() -> Agent[LeadDeps, str]:
    return Agent(
        _build_mock(),
        output_type=str,
        deps_type=LeadDeps,
        instructions="Run the control tests the researcher asks for.",
        tools=[
            Tool(run_control_tests_on_step, sequential=True),
            Tool(peek_records),
        ],
        name="controls",
        defer_model_check=True,
    )


def _build_deps(state: TurnState, context: Context) -> LeadDeps:
    pipeline = PipelineState(
        conversation_id=state.conversation_id,
        user_id=state.user_id,
        site_id=state.site_id,
        mode=state.mode,
        user_prompt=state.user_prompt,
        domain=StrategyDomainState(),
    )
    return LeadDeps(
        state=pipeline,
        intent=None,
        runtime=context,
        retrieved_memories=[],
    )


def _build_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[TurnState, Context, TurnState, TurnState]:
    return single_agent_graph(
        checkpointer=checkpointer,
        state_type=TurnState,
        context_type=Context,
        build_agent=_build_agent,
        build_deps=_build_deps,
        charge_usage=charge_usage,
    )


def _build_spec() -> AssistantSpec:
    """Served under site help's id, so the turn needs no WDK identity."""
    return AssistantSpec(
        assistant_id=SITE_HELP_ASSISTANT_ID,
        build_graph=_build_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=_build_mock,
    )


@pytest.fixture
def controls_assistant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(registry, "build_site_help_spec", _build_spec)
    get_assistant_registry.cache_clear()
    yield
    get_assistant_registry.cache_clear()


@pytest.fixture
def failing_second_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool succeeds on the first step and raises on the second."""

    async def _run_step(
        *,
        site_id: str,
        wdk_step_id: int,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
    ) -> ControlOutcome:
        del site_id, negative_controls
        if wdk_step_id == _STEP_B:
            msg = "WDK rejected step 440230653"
            raise RuntimeError(msg)
        found = positive_controls or []
        return ControlOutcome(
            step_id=wdk_step_id,
            estimated_size=132,
            positive_intersection=len(found),
            positive_controls_count=len(found),
            positive_recall=1.0,
            positive_intersection_ids=found,
            positive_missing_ids=[],
            negative_intersection=0,
            negative_controls_count=0,
            negative_false_positive_rate=None,
            negative_intersection_ids=[],
        )

    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _run_step)


@pytest.fixture
def controls_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run_step(
        *,
        site_id: str,
        wdk_step_id: int,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
    ) -> ControlOutcome:
        del site_id
        found = positive_controls or []
        return ControlOutcome(
            step_id=wdk_step_id,
            estimated_size=132,
            positive_intersection=len(found),
            positive_controls_count=len(found),
            positive_recall=1.0 if found else None,
            positive_intersection_ids=found,
            positive_missing_ids=[],
            negative_intersection=0,
            negative_controls_count=len(negative_controls or []),
            negative_false_positive_rate=None,
            negative_intersection_ids=[],
        )

    async def _export(
        result: ControlOutcome,
        name: str,
    ) -> ControlOutcome:
        del name
        return result

    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _run_step)
    monkeypatch.setattr(control_tests_impl, "attach_control_downloads", _export)


async def _make_user() -> UUID:
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()
    return user_id


async def _turn(
    app: FastAPI,
    user_id: UUID,
    jobs: InMemoryConnector,
    conversation_id: UUID,
) -> list[dict[str, Any]]:
    body = chat_post_body(conversation_id, _PROMPT)
    body["assistantId"] = SITE_HELP_ASSISTANT_ID
    queued = len(chat_turn_jobs(jobs))
    async with client_for(app, user_id) as client:
        client.headers[WDK_AUTH_HEADER] = "t"
        post = asyncio.create_task(
            client.post("/api/v1/chat", json=body, timeout=60.0),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(jobs, queued),
            timeout=20.0,
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=60.0)
    assert response.status_code == 200, response.text
    return parse_sse_body(response.text)


def _durable_payloads(jobs: InMemoryConnector) -> list[dict[str, Any]]:
    return [
        job["args"]
        for job in sorted(jobs.jobs.values(), key=lambda j: j["id"])
        if job["task_name"] == _DURABLE_TASK
    ]


async def _work_the_job(payload: dict[str, Any]) -> None:
    register_all_tools()
    await run_durable_task(
        tool_name=_TOOL,
        task_id=str(payload["task_id"]),
        thread_id=str(payload["thread_id"]),
        args=payload["args"],
        veupathdb_auth_token=payload["veupathdb_auth_token"],
    )


async def _rows(conversation_id: UUID) -> list[ConversationEvent]:
    async with async_session_factory() as session:
        found = await session.scalars(
            select(ConversationEvent)
            .where(ConversationEvent.conversation_id == conversation_id)
            .order_by(ConversationEvent.id),
        )
        return list(found)


def _types(rows: list[ConversationEvent]) -> list[str]:
    return [str(row.chunk.get("type")) for row in rows]


def _prose(rows: list[ConversationEvent]) -> str:
    return "".join(
        str(row.chunk.get("delta", ""))
        for row in rows
        if row.chunk.get("type") == "text-delta"
    )


async def _statuses(conversation_id: UUID) -> list[tuple[str, str]]:
    async with async_session_factory() as session:
        found = await session.scalars(
            select(BackgroundTask)
            .where(BackgroundTask.conversation_id == conversation_id)
            .order_by(BackgroundTask.created_at),
        )
        return [(str(task.tool_call_id), str(task.status)) for task in found]


@pytest.mark.usefixtures("controls_assistant", "controls_wire")
async def test_the_step_defers_two_jobs_and_parks_both_calls(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = await _make_user()
    conversation_id = uuid4()

    chunks = await _turn(app, user_id, in_memory_jobs, conversation_id)

    types = [chunk["type"] for chunk in chunks]
    assert "error" not in types
    started = [c for c in chunks if c["type"] == "data-background-task-started"]
    assert len(started) == 2
    assert await _statuses(conversation_id) == [
        (_CALL_A, "pending"),
        (_CALL_B, "pending"),
    ]


@pytest.mark.usefixtures("controls_assistant", "controls_wire")
async def test_the_first_task_to_finish_opens_no_completion_turn(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id)
    payloads = _durable_payloads(in_memory_jobs)
    assert len(payloads) == 2

    await _work_the_job(payloads[0])

    types = _types(await _rows(conversation_id))
    assert types.count("data-task-completed") == 1
    after = types[types.index("data-task-completed") :]
    assert "start" not in after
    assert "error" not in after
    assert await _statuses(conversation_id) == [
        (_CALL_A, "result_ready"),
        (_CALL_B, "pending"),
    ]


@pytest.mark.usefixtures("controls_assistant", "controls_wire")
async def test_the_last_task_resumes_the_run_with_every_answer(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    del patch_app_db_engine, db_cleaner
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id)
    payloads = _durable_payloads(in_memory_jobs)

    await _work_the_job(payloads[0])
    await _work_the_job(payloads[1])

    rows = await _rows(conversation_id)
    types = _types(rows)
    assert "error" not in types
    assert "data-turn-failed" not in types
    assert types.count("data-task-completed") == 2
    assert f"Controls ran on {_STEP_A}:success, {_STEP_B}:success." in _prose(rows)
    summaries = [
        row.chunk["data"]
        for row in rows
        if row.chunk.get("type") == "data-tool-summary"
        and row.chunk["data"]["toolCallId"] in {_CALL_A, _CALL_B}
    ]
    assert [s["toolCallId"] for s in summaries] == [_CALL_A, _CALL_B]
    assert {s["summary"] for s in summaries} == {
        "1 of 1 positive controls recovered",
    }
    assert await _statuses(conversation_id) == [
        (_CALL_A, "complete"),
        (_CALL_B, "complete"),
    ]


@pytest.mark.usefixtures("controls_assistant", "controls_wire", "failing_second_step")
async def test_a_failed_task_still_answers_its_call_beside_the_one_that_worked(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
) -> None:
    """The run owes a result for every call, so a failure answers its own."""
    del patch_app_db_engine, db_cleaner
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id)
    payloads = _durable_payloads(in_memory_jobs)

    await _work_the_job(payloads[0])
    await _work_the_job(payloads[1])

    rows = await _rows(conversation_id)
    assert "error" not in _types(rows)
    assert f"Controls ran on {_STEP_A}:success, none:failed." in _prose(rows)
    outcomes = [
        (row.chunk["data"]["status"], row.chunk["data"].get("error"))
        for row in rows
        if row.chunk.get("type") == "data-task-completed"
    ]
    assert outcomes[0] == ("success", None)
    assert outcomes[1][0] == "failed"
    assert "WDK rejected step 440230653" in str(outcomes[1][1])
    assert await _statuses(conversation_id) == [
        (_CALL_A, "complete"),
        (_CALL_B, "failed"),
    ]
