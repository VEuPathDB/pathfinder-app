"""The completion turn runs under the picks the deferring request carried.

One agent over the real turn graph, the real checkpointer, the real durable
decorator and the real runner. Only the model and the EDA wire are doubles.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.single_agent import single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.models.scripted import (
    RoleMarkers,
    RoleScript,
    ScriptedModel,
    ScriptedPart,
    scripted_call,
    scripted_text,
    tool_return_parts,
)
from assistant_core.persistence.models import BackgroundTask
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import ReasoningEffort
from assistant_core.spec import AssistantSpec, TurnContextRequest
from assistant_core.tasks.runner import run_durable_task
from fastapi import FastAPI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from procrastinate.testing import InMemoryConnector
from pydantic import BaseModel
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import select

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.eda_compute import run_eda_compute
from pathfinder.assistants import registry
from pathfinder.assistants.pathfinder_spec import build_turn_context
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.assistants.site_help.spec import (
    SITE_HELP_ASSISTANT_ID,
    build_initial_state,
    charge_usage,
)
from pathfinder.jobs.impls import register_all_tools
from pathfinder.persistence.models import User
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import WDK_AUTH_HEADER, client_for
from pathfinder.tests.integration.jobs import _eda_wire

_PROMPT = "compare the febrile samples against the normal ones"
_TOOL = "run_eda_compute"
_DURABLE_TASK = f"durable:{_TOOL}"

_PINNED_MODEL = "openai:gpt-5.6-luna"
_PINNED_EFFORT = "high"


@dataclass
class _Picks:
    """The per-phase picks one turn built its context from."""

    models: dict[str, str] = field(default_factory=dict)
    reasoning: dict[str, ReasoningEffort] = field(default_factory=dict)


_SEEN: list[_Picks] = []


class _Resumed(BaseModel):
    """What the completion turn hands back to the parked tool call."""

    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


def _script(messages: list[ModelMessage]) -> ScriptedPart:
    """Call the compute once, then answer with the count the worker returned."""
    returns = tool_return_parts(messages)
    if returns:
        resumed = _Resumed.model_validate(returns[-1].content)
        if resumed.result is None:
            return scripted_text(f"The compute {resumed.status}.")
        return scripted_text(f"{resumed.result['retained']} genes pass.")
    return scripted_call(
        _TOOL,
        {
            "identifier_variable": {
                "entityId": "ENT_fd574cd6",
                "variableId": "VEUPATHDB_GENE_ID",
            },
            "value_variable": {
                "entityId": "ENT_fd574cd6",
                "variableId": "SEQUENCE_READ_COUNT_SENSE",
            },
            "comparator_variable": {
                "entityId": "ENT_8151325d",
                "variableId": "VAR_081ab087",
            },
            "group_a_labels": ["normal"],
            "group_b_labels": ["febrile"],
            "method": "DESeq",
        },
    )


_SCRIPTS: dict[str, RoleScript] = {"eda": _script}
_MODEL = ScriptedModel(
    roles=(RoleMarkers(role="eda", markers=frozenset({_TOOL})),),
    scripts=_SCRIPTS,
    unknown=_script,
)


def _build_mock() -> FunctionModel:
    return _MODEL.as_function_model()


def _build_agent() -> Agent[LeadDeps, str]:
    return Agent(
        _build_mock(),
        output_type=str,
        deps_type=LeadDeps,
        instructions="Run the compute the researcher asks for and report it.",
        tools=[Tool(run_eda_compute, sequential=True)],
        name="eda",
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


async def _recording_turn_context(request: TurnContextRequest) -> Context:
    """The production context factory, with this turn's picks recorded."""
    _SEEN.append(
        _Picks(
            models=dict(request.phase_models),
            reasoning=dict(request.phase_reasoning),
        ),
    )
    return await build_turn_context(request)


def _build_spec() -> AssistantSpec:
    """Served under site help's id, so the turn needs no WDK identity."""
    return AssistantSpec(
        assistant_id=SITE_HELP_ASSISTANT_ID,
        build_graph=_build_graph,
        build_initial_state=build_initial_state,
        build_turn_context=_recording_turn_context,
        build_mock_model=_build_mock,
    )


@pytest.fixture
def recording_assistant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _SEEN.clear()
    monkeypatch.setattr(registry, "build_site_help_spec", _build_spec)
    get_assistant_registry.cache_clear()
    yield
    get_assistant_registry.cache_clear()
    _SEEN.clear()


@pytest.fixture
def recording_worker(recording_assistant: None, worker_seams: None) -> None:
    """The worker's seams, over the registry this module records through."""
    del recording_assistant, worker_seams


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
    *,
    picks: dict[str, Any],
) -> None:
    body = chat_post_body(conversation_id, _PROMPT)
    body["assistantId"] = SITE_HELP_ASSISTANT_ID
    body.update(picks)
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


def _durable_payload(jobs: InMemoryConnector) -> dict[str, Any]:
    deferred = [job for job in jobs.jobs.values() if job["task_name"] == _DURABLE_TASK]
    assert deferred, "the durable compute deferred no job"
    args: dict[str, Any] = deferred[0]["args"]
    return args


async def _work_the_job(payload: dict[str, Any]) -> None:
    register_all_tools()
    await run_durable_task(
        tool_name=_TOOL,
        task_id=str(payload["task_id"]),
        thread_id=str(payload["thread_id"]),
        args=payload["args"],
        job_context=payload["job_context"],
    )


async def _task_row(conversation_id: UUID) -> BackgroundTask:
    async with async_session_factory() as session:
        found = await session.scalars(
            select(BackgroundTask).where(
                BackgroundTask.conversation_id == conversation_id,
            ),
        )
        rows = list(found)
    assert len(rows) == 1
    return rows[0]


_PINNED = {
    "phaseModels": {"lead": _PINNED_MODEL},
    "phaseReasoning": {"lead": _PINNED_EFFORT},
}


async def test_the_deferred_task_row_carries_the_turn_s_picks(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    recording_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The picks are request-scoped, so the row that outlives the request holds them."""
    del patch_app_db_engine, db_cleaner, recording_worker
    wire = _eda_wire.install(monkeypatch, "complete")
    user_id = await _make_user()
    conversation_id = uuid4()

    await _turn(app, user_id, in_memory_jobs, conversation_id, picks=_PINNED)
    await wire.client.close()

    row = await _task_row(conversation_id)
    assert row.phase_overrides == {
        "models": {"lead": _PINNED_MODEL},
        "reasoning": {"lead": _PINNED_EFFORT},
    }


async def test_the_completion_turn_runs_under_the_pinned_model(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    recording_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both halves of one investigation resolve the same model and effort."""
    del patch_app_db_engine, db_cleaner, recording_worker
    wire = _eda_wire.install(monkeypatch, "complete")
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id, picks=_PINNED)

    await _work_the_job(_durable_payload(in_memory_jobs))
    await wire.client.close()

    assert len(_SEEN) == 2
    assert _SEEN[0] == _SEEN[1]
    assert _SEEN[1].models == {"lead": _PINNED_MODEL}
    assert _SEEN[1].reasoning == {"lead": _PINNED_EFFORT}


async def test_a_turn_that_pins_nothing_leaves_the_row_empty(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    recording_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request with no picks pins nothing on the completion turn either."""
    del patch_app_db_engine, db_cleaner, recording_worker
    wire = _eda_wire.install(monkeypatch, "complete")
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id, picks={})

    await _work_the_job(_durable_payload(in_memory_jobs))
    await wire.client.close()

    row = await _task_row(conversation_id)
    assert row.phase_overrides == {"models": {}, "reasoning": {}}
    assert len(_SEEN) == 2
    assert _SEEN[1].models == {}
