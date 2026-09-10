from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
    NewBackgroundTask,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.declaration import (
    declare_durable_tool,
    empty_durable_tools,
    register_durable_impl,
)
from assistant_core.tasks.progress import TaskProgressEmitter
from assistant_core.tasks.runner import run_durable_task

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.fixture(autouse=True)
def _clean_tool_registry() -> Iterator[None]:
    with empty_durable_tools():
        yield


async def _ensure_user_and_chat(user_id: UUID, conversation_id: UUID) -> None:
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


@pytest.mark.asyncio
async def test_runner_executes_tool_and_marks_complete(
    db_cleaner: None, patch_app_db_engine: None, worker_seams: None
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams

    progress_events: list[tuple[float, str]] = []

    async def _echo_impl(
        *,
        context: Any,
        task_id: UUID,
        progress: TaskProgressEmitter,
        memory_store: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context, task_id, memory_store
        await progress.update(percent=0.5, message="halfway")
        progress_events.append((0.5, "halfway"))
        return {"echoed": kwargs.get("value")}

    register_durable_impl(
        declare_durable_tool(tool_name="test_echo", estimated_duration_seconds=10),
        _echo_impl,
    )

    user_id = uuid4()
    conversation_id = uuid4()
    await _ensure_user_and_chat(user_id, conversation_id)

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="test_echo",
            args={"args": [], "kwargs": {"value": 42}},
            tool_call_id="call_test_echo",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )

    await run_durable_task(
        tool_name="test_echo",
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": {"value": 42}},
    )

    t = await repo.get(task_id=task_id)
    assert t is not None
    assert t.status in ("complete", "resuming", "result_ready")
    assert t.result == {"echoed": 42}
    assert progress_events == [(0.5, "halfway")]


@pytest.mark.asyncio
async def test_runner_marks_failed_on_exception(
    db_cleaner: None, patch_app_db_engine: None, worker_seams: None
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams

    async def _boom_impl(
        *,
        context: Any,
        task_id: UUID,
        progress: TaskProgressEmitter,
        memory_store: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context, task_id, progress, memory_store, kwargs
        msg = "kaboom"
        raise RuntimeError(msg)

    register_durable_impl(
        declare_durable_tool(tool_name="test_boom", estimated_duration_seconds=10),
        _boom_impl,
    )

    user_id = uuid4()
    conversation_id = uuid4()
    await _ensure_user_and_chat(user_id, conversation_id)

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="test_boom",
            args={"args": [], "kwargs": {}},
            tool_call_id="call_test_boom",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )

    await run_durable_task(
        tool_name="test_boom",
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": {}},
    )

    t = await repo.get(task_id=task_id)
    assert t is not None
    assert t.status == "failed"
    assert t.error is not None
    assert "kaboom" in t.error


@pytest.mark.asyncio
async def test_runner_marks_failed_when_tool_unknown(
    db_cleaner: None, patch_app_db_engine: None
) -> None:
    del db_cleaner, patch_app_db_engine

    user_id = uuid4()
    conversation_id = uuid4()
    await _ensure_user_and_chat(user_id, conversation_id)

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="nonexistent_tool",
            args={"args": [], "kwargs": {}},
            tool_call_id="call_nonexistent_tool",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )

    await run_durable_task(
        tool_name="nonexistent_tool",
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": {}},
    )

    t = await repo.get(task_id=task_id)
    assert t is not None
    assert t.status == "failed"
    assert t.error is not None
    assert "nonexistent_tool" in t.error
