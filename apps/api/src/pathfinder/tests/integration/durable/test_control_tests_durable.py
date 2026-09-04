from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select

from pathfinder.jobs.impls import control_tests_impl, register_all_tools
from pathfinder.jobs.impls.control_tests_impl import (
    run_control_tests_on_step_impl,
)
from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.jobs.registry import TOOL_REGISTRY
from pathfinder.jobs.runner import run_durable_task
from pathfinder.persistence.models import BackgroundTask, TaskProgress, User
from pathfinder.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
    NewBackgroundTask,
)
from pathfinder.services.tool_payloads import ControlOutcome, DownloadLinks


async def _seed_user_chat(user_id: UUID, conversation_id: UUID) -> None:
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
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
) -> ControlOutcome:
    del site_id
    pos = positive_controls or []
    neg = negative_controls or []
    return ControlOutcome(
        step_id=wdk_step_id,
        estimated_size=100,
        positive_intersection=len(pos),
        positive_controls_count=len(pos),
        positive_recall=1.0 if pos else None,
        positive_intersection_ids=pos,
        positive_missing_ids=[],
        negative_intersection=0,
        negative_controls_count=len(neg),
        negative_false_positive_rate=0.0 if neg else None,
        negative_intersection_ids=[],
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
    before = set(TOOL_REGISTRY)
    register_all_tools()
    assert "run_control_tests_on_step" in TOOL_REGISTRY
    assert TOOL_REGISTRY["run_control_tests_on_step"] is (
        run_control_tests_on_step_impl
    )
    # idempotent
    register_all_tools()
    # cleanup
    for key in set(TOOL_REGISTRY) - before:
        TOOL_REGISTRY.pop(key, None)


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
        context=_FakeContext(site_id="plasmodb"),
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
                    select(TaskProgress)
                    .where(TaskProgress.task_id == task_id)
                    .order_by(TaskProgress.id)
                )
            ).scalars()
        )

    assert len(rows) >= 1
    assert rows[0].percent <= rows[-1].percent


class _FakeContext:
    def __init__(self, site_id: str) -> None:
        self.site_id = site_id


@pytest.mark.asyncio
async def test_run_durable_task_wiring_control_tests_end_to_end(
    db_cleaner: None,
    patch_app_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_cleaner, patch_app_db_engine
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
