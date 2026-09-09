from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory

from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
    NewBackgroundTask,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.mark.asyncio
async def test_create_mark_transitions(
    db_cleaner: None, patch_app_db_engine: None
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
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

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="test",
            args={"kwargs": {}},
            tool_call_id="call_test_transitions",
            phase_overrides={},
            estimated_duration_seconds=30,
        ),
    )
    await repo.mark_running(task_id=task_id)
    task = await repo.get(task_id=task_id)
    assert task is not None
    assert task.status == "running"
    assert task.started_at is not None
    # The row names the call the completion turn answers.
    assert task.tool_call_id == "call_test_transitions"

    await repo.mark_result_ready(task_id=task_id, result={"ok": True})
    task = await repo.get(task_id=task_id)
    assert task is not None
    assert task.status == "result_ready"
    assert task.result == {"ok": True}

    await repo.mark_resuming(task_id=task_id)
    task = await repo.get(task_id=task_id)
    assert task is not None
    assert task.status == "resuming"

    await repo.mark_complete(task_id=task_id)
    task = await repo.get(task_id=task_id)
    assert task is not None
    assert task.status == "complete"
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_mark_failed(db_cleaner: None, patch_app_db_engine: None) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    conversation_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
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

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="test",
            args={},
            tool_call_id="call_test_failed",
            phase_overrides={},
            estimated_duration_seconds=30,
        ),
    )
    await repo.mark_failed(task_id=task_id, error="boom")
    task = await repo.get(task_id=task_id)
    assert task is not None
    assert task.status == "failed"
    assert task.error == "boom"
    assert task.completed_at is not None
