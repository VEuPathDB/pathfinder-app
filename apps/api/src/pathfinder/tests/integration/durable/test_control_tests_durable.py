from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    TaskProgressRow,
)
from assistant_core.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
    NewBackgroundTask,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.declaration import durable_impl
from assistant_core.tasks.progress import TaskProgressEmitter
from assistant_core.tasks.runner import run_durable_task
from sqlalchemy import select
from veupathdb_mcp.controls import (
    ControlSetData,
    ControlTargetData,
    ControlTestResult,
)
from veupathdb_mcp.tool_payloads import ControlOutcome, DownloadLinks

from pathfinder.jobs.impls import control_tests_impl, register_all_tools
from pathfinder.jobs.impls.control_tests_impl import (
    run_control_tests_on_step_impl,
)
from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests._support.job_context import job_context


async def _seed_user_chat(user_id: UUID, conversation_id: UUID) -> None:
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="",
            )
        )
        await session.commit()


async def _fake_run_step(
    *,
    site_id: str,
    wdk_step_id: int,
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
) -> ControlTestResult:
    del site_id
    pos = positive_controls or []
    neg = negative_controls or []
    return ControlTestResult(
        site_id="plasmodb",
        record_type="transcript",
        target=ControlTargetData(step_id=wdk_step_id, estimated_size=100),
        positive=ControlSetData(
            controls_count=len(pos),
            intersection_count=len(pos),
            intersection_ids_sample=pos,
            recall=1.0 if pos else None,
        )
        if pos
        else None,
        negative=ControlSetData(
            controls_count=len(neg),
            intersection_count=0,
            false_positive_rate=0.0 if neg else None,
        )
        if neg
        else None,
    )


async def _fake_export(result: ControlOutcome, name: str) -> ControlOutcome:
    del name
    result.downloads = DownloadLinks(
        json_url="https://example/export.json",
        expires_in_seconds=3600,
    )
    return result


@pytest.mark.asyncio
async def test_register_all_tools_populates_registry() -> None:
    register_all_tools()
    assert durable_impl("run_control_tests_on_step") is run_control_tests_on_step_impl
    register_all_tools()
    assert durable_impl("run_control_tests_on_step") is run_control_tests_on_step_impl


@pytest.mark.asyncio
async def test_control_tests_impl_emits_progress_and_returns_dict(
    db_cleaner: None,
    patch_app_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_cleaner, patch_app_db_engine
    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _fake_run_step)
    monkeypatch.setattr(control_tests_impl, "attach_control_downloads", _fake_export)

    user_id = uuid4()
    conversation_id = uuid4()
    task_id = uuid4()
    await _seed_user_chat(user_id, conversation_id)

    async with async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="run_control_tests_on_step",
                status="running",
                args={},
                estimated_duration_seconds=10,
            )
        )
        await session.commit()

    progress = TaskProgressEmitter(
        task_id=task_id,
        conversation_id=conversation_id,
        session_factory=async_session_factory,
    )
    context = object()  # impl uses only site_id via deps.context.site_id? No — fake

    result = await run_control_tests_on_step_impl(
        context=job_context(),
        task_id=task_id,
        progress=progress,
        memory_store=None,
        wdk_step_id=123,
        positive_controls=["g1", "g2"],
        negative_controls=["g9"],
    )
    del context

    assert isinstance(result, dict)
    assert result["stepId"] == 123
    assert result["positiveIntersection"] == 2
    assert result["downloads"]["jsonUrl"] == "https://example/export.json"

    async with async_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(TaskProgressRow)
                    .where(TaskProgressRow.task_id == task_id)
                    .order_by(TaskProgressRow.id)
                )
            ).scalars()
        )

    assert len(rows) >= 1
    assert rows[0].percent <= rows[-1].percent


@pytest.mark.asyncio
async def test_run_durable_task_wiring_control_tests_end_to_end(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _fake_run_step)
    monkeypatch.setattr(control_tests_impl, "attach_control_downloads", _fake_export)
    register_all_tools()

    user_id = uuid4()
    conversation_id = uuid4()
    await _seed_user_chat(user_id, conversation_id)

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="run_control_tests_on_step",
            args={
                "args": [],
                "kwargs": {
                    "wdk_step_id": 42,
                    "positive_controls": ["a", "b"],
                    "negative_controls": [],
                },
            },
            tool_call_id="call_run_control_tests_on_step",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )

    await run_durable_task(
        tool_name="run_control_tests_on_step",
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={
            "args": [],
            "kwargs": {
                "wdk_step_id": 42,
                "positive_controls": ["a", "b"],
                "negative_controls": [],
            },
        },
    )

    t = await repo.get(task_id=task_id)
    assert t is not None
    assert t.status in ("complete", "resuming", "result_ready")
    result_payload: dict[str, Any] | None = t.result
    assert result_payload is not None
    assert result_payload["stepId"] == 42
