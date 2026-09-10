"""run_eda_compute defers its call, and the completion turn carries the summary.

One agent over the real turn graph, the real checkpointer and the real event
writer. Only the model and the EDA wire are doubles: the tool, the decorator,
the worker impl and the runner are the production ones.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
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
from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.spec import AssistantSpec
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
from pathfinder.services.eda.binding import (
    bind_conversation_analysis,
    bound_conversation_analysis,
)
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import WDK_AUTH_HEADER, client_for
from pathfinder.tests.integration.jobs import _eda_wire

_PROMPT = "compare the febrile samples against the normal ones"
_TOOL = "run_eda_compute"
_DURABLE_TASK = f"durable:{_TOOL}"


class _Resumed(BaseModel):
    """What the completion turn hands back to the parked tool call."""

    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


def _script(messages: list[ModelMessage]) -> ScriptedPart:
    """Call the compute once, then quote the numbers the worker returned."""
    returns = tool_return_parts(messages)
    if returns:
        resumed = _Resumed.model_validate(returns[-1].content)
        if resumed.result is None:
            return scripted_text(f"The compute {resumed.status}: {resumed.error}")
        return scripted_text(
            f"{resumed.result['retained']} of "
            f"{resumed.result['genesTested']} genes pass.",
        )
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
def eda_assistant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(registry, "build_site_help_spec", _build_spec)
    get_assistant_registry.cache_clear()
    yield
    get_assistant_registry.cache_clear()


@pytest.fixture
def eda_worker(eda_assistant: None, worker_seams: None) -> None:
    """The worker's seams, over the registry this module records through."""
    del eda_assistant, worker_seams


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
        # The compute reads EDA as the caller, so the turn carries a token.
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


def _durable_payload(jobs: InMemoryConnector) -> dict[str, Any]:
    deferred = [job for job in jobs.jobs.values() if job["task_name"] == _DURABLE_TASK]
    assert deferred, "the durable compute deferred no job"
    args: dict[str, Any] = deferred[0]["args"]
    return args


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


async def _work_the_job(payload: dict[str, Any]) -> None:
    register_all_tools()
    await run_durable_task(
        tool_name=_TOOL,
        task_id=str(payload["task_id"]),
        thread_id=str(payload["thread_id"]),
        args=payload["args"],
        job_context=payload["job_context"],
    )


async def test_the_turn_ends_with_a_background_task_started_part(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    eda_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dispatcher's clean end: the tab closes and the work continues."""
    del patch_app_db_engine, db_cleaner, eda_worker
    _eda_wire.install(monkeypatch, "complete")
    user_id = await _make_user()
    conversation_id = uuid4()

    chunks = await _turn(app, user_id, in_memory_jobs, conversation_id)

    types = [chunk["type"] for chunk in chunks]
    assert "data-background-task-started" in types
    assert "error" not in types
    assert types[-2:] == ["finish", "done"]
    started = next(
        chunk for chunk in chunks if chunk["type"] == "data-background-task-started"
    )
    assert started["data"]["toolName"] == _TOOL
    assert started["data"]["estimatedDurationSeconds"] == 120
    assert _durable_payload(in_memory_jobs)["args"]["kwargs"]["method"] == "DESeq"


async def test_the_resumed_turn_carries_the_compute_summary_into_the_prose(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    eda_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scripted model is given the resumed dict and must quote its numbers."""
    del patch_app_db_engine, db_cleaner, eda_worker
    wire = _eda_wire.install(monkeypatch, "complete")
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id)

    await _work_the_job(_durable_payload(in_memory_jobs))
    await wire.client.close()

    prose = _prose(await _rows(conversation_id))
    assert (
        f"{_eda_wire.FIXTURE_RETAINED} of {_eda_wire.FIXTURE_ROWS} genes pass." in prose
    )


async def test_the_resumed_chunks_land_in_conversation_events(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    eda_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reconnecting client replays the same rows the resume wrote."""
    del patch_app_db_engine, db_cleaner, eda_worker
    wire = _eda_wire.install(monkeypatch, "complete")
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id)
    before = len(await _rows(conversation_id))

    await _work_the_job(_durable_payload(in_memory_jobs))
    await wire.client.close()

    rows = await _rows(conversation_id)
    types = _types(rows)
    assert len(rows) > before
    assert "data-task-completed" in types
    resumed = types[types.index("data-task-completed") :]
    assert "text-delta" in resumed
    assert resumed[-1] == "done"


async def test_a_failed_job_appends_a_task_completed_event_with_the_error(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    eda_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner, eda_worker
    wire = _eda_wire.install(monkeypatch, "no-such-job", "failed")
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id)

    await _work_the_job(_durable_payload(in_memory_jobs))
    await wire.client.close()

    completed = [
        row.chunk
        for row in await _rows(conversation_id)
        if row.chunk.get("type") == "data-task-completed"
    ]
    assert len(completed) == 1
    assert completed[0]["data"]["status"] == "failed"
    assert "failed" in completed[0]["data"]["error"]


async def test_the_compute_announces_the_analysis_under_a_greater_revision(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    eda_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two surfaces edit one analysis, so every mutation moves the counter."""
    del patch_app_db_engine, db_cleaner, eda_worker
    wire = _eda_wire.install(monkeypatch, "complete", real_binding=True)
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id)
    await bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=_eda_wire.DATASET,
        analysis_id=_eda_wire.ANALYSIS,
    )
    before = await bound_conversation_analysis(conversation_id=conversation_id)
    assert before is not None

    await _work_the_job(_durable_payload(in_memory_jobs))
    await wire.client.close()

    states = [
        row.chunk
        for row in await _rows(conversation_id)
        if row.chunk.get("type") == "data-eda.analysis-state"
    ]
    assert len(states) == 1
    data = states[0]["data"]
    assert data["revision"] > before.revision
    assert data["analysisId"] == _eda_wire.ANALYSIS
    assert data["numComputations"] == 1
    after = await bound_conversation_analysis(conversation_id=conversation_id)
    assert after is not None
    assert after.revision == data["revision"]


async def test_the_volcano_reaches_conversation_events_after_the_state(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    eda_worker: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The viz belongs to the revision the state announces, so it follows it."""
    del patch_app_db_engine, db_cleaner, eda_worker
    wire = _eda_wire.install(monkeypatch, "complete", real_binding=True)
    user_id = await _make_user()
    conversation_id = uuid4()
    await _turn(app, user_id, in_memory_jobs, conversation_id)
    await bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=_eda_wire.DATASET,
        analysis_id=_eda_wire.ANALYSIS,
    )

    await _work_the_job(_durable_payload(in_memory_jobs))
    await wire.client.close()

    rows = await _rows(conversation_id)
    types = _types(rows)
    assert types.count("data-eda.viz") == 1
    assert types.index("data-eda.analysis-state") < types.index("data-eda.viz")
    viz = next(row.chunk for row in rows if row.chunk.get("type") == "data-eda.viz")
    data = viz["data"]
    assert data["chart"] == "volcano"
    assert data["analysisId"] == _eda_wire.ANALYSIS
    assert data["totalPoints"] == _eda_wire.FIXTURE_ROWS
    assert data["retainedPoints"] == _eda_wire.FIXTURE_RETAINED
    assert data["points"][0]["retained"] is True
    # The persisted row keeps the null, so the card can count the unplaced gene.
    assert len(data["points"]) == _eda_wire.FIXTURE_ROWS
    assert [p["pointId"] for p in data["points"] if p["pValue"] is None] == [
        "PF3D7_MIT04200",
    ]
