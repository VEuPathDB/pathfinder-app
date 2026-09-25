"""Two durable calls from one model step are answered by one completion turn.

One agent over the real turn graph, the real checkpointer, the real event
writer and the real runner. Only the model and the control-test wire are
doubles. The first task to finish opens no turn; the last one resumes the run
with an answer for every parked call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import BackgroundTask, ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.runner import run_durable_task
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStep
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.assistants import registry
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.jobs.impls import control_tests_impl, register_all_tools
from pathfinder.persistence.models import User
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import WDK_AUTH_HEADER, client_for
from pathfinder.tests.integration.jobs._controls_wire import (
    CALL_A,
    CALL_B,
    STEP_A,
    STEP_B,
    TOOL,
    build_spec,
)

_PROMPT = "run control tests on both steps and show me a few records"
_DURABLE_TASK = f"durable:{TOOL}"


# Every test here drives the worker arc: the registry this module records
# through, the seams the worker installs over it, and the WDK double.
pytestmark = pytest.mark.usefixtures(
    "controls_assistant", "worker_seams", "controls_wire"
)


@pytest.fixture
def controls_assistant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(registry, "build_site_help_spec", build_spec)
    get_assistant_registry.cache_clear()
    yield
    get_assistant_registry.cache_clear()


@pytest.fixture
def failing_second_step(
    controls_wire: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tool succeeds on the first step and raises on the second.

    It replaces the working wire, so it is installed after it.
    """
    del controls_wire

    async def _run_step(
        *,
        site_id: str,
        wdk_step_id: int,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
    ) -> ControlTestResult:
        del site_id, negative_controls
        if wdk_step_id == STEP_B:
            msg = "WDK rejected step 440230653"
            raise RuntimeError(msg)
        found = positive_controls or []
        return ControlTestResult(
            site_id="plasmodb",
            record_type="transcript",
            target=ControlTargetData(step_id=wdk_step_id, estimated_size=132),
            positive=PositiveControls(recovered_ids=found, missed_ids=[])
            if found
            else None,
        )

    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _run_step)


class _StepsTheAccountDoesNotHold:
    """The account's steps: the tested ids are not among them."""

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        msg = f"step {step_id} is not in this account"
        raise WDKError(msg, 404)


@pytest.fixture
def controls_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run_step(
        *,
        site_id: str,
        wdk_step_id: int,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
    ) -> ControlTestResult:
        del site_id
        found = positive_controls or []
        neg = negative_controls or []
        return ControlTestResult(
            site_id="plasmodb",
            record_type="transcript",
            target=ControlTargetData(step_id=wdk_step_id, estimated_size=132),
            positive=PositiveControls(recovered_ids=found, missed_ids=[])
            if found
            else None,
            negative=NegativeControls(admitted_ids=[], excluded_ids=neg)
            if neg
            else None,
        )

    async def _export(
        result: ControlOutcome,
        name: str,
    ) -> ControlOutcome:
        del name
        return result

    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _run_step)
    monkeypatch.setattr(control_tests_impl, "attach_control_downloads", _export)
    monkeypatch.setattr(
        control_tests_impl,
        "get_strategy_api",
        lambda _site_id: _StepsTheAccountDoesNotHold(),
    )


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
        tool_name=TOOL,
        task_id=str(payload["task_id"]),
        thread_id=str(payload["thread_id"]),
        args=payload["args"],
        job_context=payload["job_context"],
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
        (CALL_A, "pending"),
        (CALL_B, "pending"),
    ]


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
        (CALL_A, "result_ready"),
        (CALL_B, "pending"),
    ]


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
    assert f"Controls ran on {STEP_A}:success, {STEP_B}:success." in _prose(rows)
    summaries = [
        row.chunk["data"]
        for row in rows
        if row.chunk.get("type") == "data-tool-summary"
        and row.chunk["data"]["toolCallId"] in {CALL_A, CALL_B}
    ]
    assert [s["toolCallId"] for s in summaries] == [CALL_A, CALL_B]
    assert {s["summary"] for s in summaries} == {
        (
            "1 of 1 positive controls recovered; "
            "recall 1.00, no negative controls tested; "
            "no tunable parameters"
        ),
    }
    assert await _statuses(conversation_id) == [
        (CALL_A, "complete"),
        (CALL_B, "complete"),
    ]


@pytest.mark.usefixtures("failing_second_step")
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
    assert f"Controls ran on {STEP_A}:success, none:failed." in _prose(rows)
    outcomes = [
        (row.chunk["data"]["status"], row.chunk["data"].get("error"))
        for row in rows
        if row.chunk.get("type") == "data-task-completed"
    ]
    assert outcomes[0] == ("success", None)
    assert outcomes[1][0] == "failed"
    assert "WDK rejected step 440230653" in str(outcomes[1][1])
    assert await _statuses(conversation_id) == [
        (CALL_A, "complete"),
        (CALL_B, "failed"),
    ]
