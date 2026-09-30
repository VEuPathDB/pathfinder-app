"""A worker run that parks on a durable task waits for the completion turn the
task opens, and captures that turn's reply, the way the web client reads it."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.event_writer import append_chunk
from assistant_core.graph.stream_events import (
    background_task_started_event,
    task_completed_event,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import JSONObject
from assistant_core.tasks.runner import run_durable_task
from procrastinate.testing import InMemoryConnector
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    DoneChunk,
    FinishChunk,
    StartChunk,
    TextDeltaChunk,
)
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStep
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    PositiveControls,
)
from veupathdb_mcp.tool_payloads import ControlOutcome

from pathfinder.assistants import registry
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.devtools import chat
from pathfinder.devtools.capture import RunCapture
from pathfinder.devtools.chat import (
    DEV_USER_ID,
    RunArgs,
    _body_ctx,
    _current_gate,
    _exec_via_worker,
    parse_run_args,
)
from pathfinder.devtools.gates import user_body
from pathfinder.jobs.impls import control_tests_impl, register_all_tools
from pathfinder.jobs.payloads import ChatTurnPayload
from pathfinder.persistence.repositories.user import UserRepository
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID
from pathfinder.services.conversations.begin import begin_conversation
from pathfinder.tests.integration.chat._helpers import run_deferred_chat_turns
from pathfinder.tests.integration.jobs._controls_wire import (
    STEP_A,
    STEP_B,
    TOOL,
    build_spec,
    save_the_controls,
)

_EDA = "run_eda_compute"
_TASK = UUID("0f0e0d0c-0000-4000-8000-00000000e0a1")
_REPLY = "The compute kept 430 genes: 314 up and 116 down."
_POLL_S = 0.02
_GAP_S = 0.3

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")


def _wire(chunk: BaseChunk) -> JSONObject:
    return chunk.model_dump(by_alias=True, exclude_none=True, mode="json")


async def _append(conversation_id: UUID, chunks: list[JSONObject]) -> None:
    for chunk in chunks:
        await append_chunk(conversation_id=conversation_id, chunk=chunk)


async def _opened(tmp_path: Path) -> tuple[RunArgs, RunCapture]:
    conversation_id = uuid4()
    args = parse_run_args(
        [
            "compare the two sides",
            "--site",
            "plasmodb",
            "--assistant",
            SITE_HELP_ASSISTANT_ID,
            "--via-worker",
            "--conversation-id",
            str(conversation_id),
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )
    async with async_session_factory() as session:
        await UserRepository(session).get_or_create(DEV_USER_ID)
        await begin_conversation(
            session=session,
            conversation_id=conversation_id,
            user_id=DEV_USER_ID,
            site_id="plasmodb",
            assistant_id=SITE_HELP_ASSISTANT_ID,
        )
        await session.commit()
    capture = RunCapture(
        conversation_id=conversation_id,
        turn_id=uuid4(),
        run_dir=args.run_dir,
        quiet=True,
    )
    return args, capture


async def test_the_run_waits_out_the_park_and_captures_the_answer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The parked turn's task is not listed, so only the log says a turn is owed."""
    args, capture = await _opened(tmp_path)
    conversation_id = args.conversation_id
    later: list[asyncio.Task[None]] = []

    async def _answer_later() -> None:
        await asyncio.sleep(_GAP_S)
        await _append(
            conversation_id,
            [
                _wire(task_completed_event(task_id=_TASK, status="success")),
                _wire(StartChunk(message_id="m1")),
                _wire(TextDeltaChunk(id="t1", delta=_REPLY)),
                _wire(FinishChunk(finish_reason="stop")),
                _wire(DoneChunk()),
            ],
        )

    async def _park(payload: ChatTurnPayload) -> None:
        del payload
        started = background_task_started_event(
            task_id=_TASK, tool_name=_EDA, estimated_duration_seconds=120
        )
        await _append(
            conversation_id,
            [
                _wire(StartChunk(message_id="m1")),
                _wire(started),
                _wire(FinishChunk(finish_reason="other")),
                _wire(DoneChunk()),
            ],
        )
        later.append(asyncio.create_task(_answer_later()))

    monkeypatch.setattr(chat, "_defer_chat_turn", _park)
    monkeypatch.setattr(chat, "_VIA_WORKER_POLL_S", _POLL_S)
    body = user_body(_body_ctx(args), message_id=capture.turn_id, text=args.prompt)

    await _exec_via_worker(args, capture, body, wdk_token=None)
    await asyncio.gather(*later)

    assert capture.assistant_text() == _REPLY
    assert _current_gate(capture).kind == "none"
    assert f"turn parked on {_EDA}" in capsys.readouterr().out


@pytest.fixture
def controls_assistant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(registry, "build_site_help_spec", build_spec)
    get_assistant_registry.cache_clear()
    yield
    get_assistant_registry.cache_clear()


class _NoSteps:
    """An account that holds none of the tested steps."""

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
        del site_id, negative_controls
        return ControlTestResult(
            site_id="plasmodb",
            record_type="transcript",
            target=ControlTargetData(step_id=wdk_step_id, estimated_size=132),
            positive=PositiveControls(
                recovered_ids=positive_controls or [], missed_ids=[]
            ),
        )

    async def _export(result: ControlOutcome, name: str) -> ControlOutcome:
        del name
        return result

    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _run_step)
    monkeypatch.setattr(control_tests_impl, "attach_control_downloads", _export)
    monkeypatch.setattr(
        control_tests_impl, "get_strategy_api", lambda _site_id: _NoSteps()
    )


async def _work_the_durable_jobs(jobs: InMemoryConnector) -> None:
    register_all_tools()
    for job in sorted(jobs.jobs.values(), key=lambda j: j["id"]):
        if job["task_name"] != f"durable:{TOOL}":
            continue
        payload: dict[str, Any] = job["args"]
        await run_durable_task(
            tool_name=TOOL,
            task_id=str(payload["task_id"]),
            thread_id=str(payload["thread_id"]),
            args=payload["args"],
            job_context=payload["job_context"],
        )


@pytest.mark.usefixtures("controls_assistant", "controls_wire", "worker_seams")
async def test_a_real_two_task_park_is_followed_to_the_completion_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    in_memory_jobs: InMemoryConnector,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The worker parks on two control tests; the reply names both results."""
    args, capture = await _opened(tmp_path)
    await save_the_controls(DEV_USER_ID)
    worked: list[asyncio.Task[None]] = []
    defer = chat._defer_chat_turn

    async def _work() -> None:
        await run_deferred_chat_turns()
        await asyncio.sleep(_GAP_S)
        await _work_the_durable_jobs(in_memory_jobs)

    async def _defer_and_work(payload: ChatTurnPayload) -> None:
        await defer(payload)
        worked.append(asyncio.create_task(_work()))

    monkeypatch.setattr(chat, "_defer_chat_turn", _defer_and_work)
    monkeypatch.setattr(chat, "_VIA_WORKER_POLL_S", _POLL_S)
    body = user_body(_body_ctx(args), message_id=capture.turn_id, text=args.prompt)

    await _exec_via_worker(args, capture, body, wdk_token="t")
    await asyncio.gather(*worked)

    assert capture.assistant_text() == (
        f"Controls ran on {STEP_A}:success, {STEP_B}:success."
    )
    assert capture.durable_tasks == []
    assert _current_gate(capture).kind == "none"
    assert f"turn parked on {TOOL}, {TOOL}" in capsys.readouterr().out
