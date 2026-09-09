"""Batched progress emitter commits every ``batch_size`` rows, not per call."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import func, select

from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.persistence.models import BackgroundTask, TaskProgress, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.mark.asyncio
async def test_batched_emitter_flushes_on_batch_full(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id, conversation_id, task_id = uuid4(), uuid4(), uuid4()
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
        await session.flush()
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="t",
                status="running",
                args={},
                estimated_duration_seconds=30,
            )
        )
        await session.commit()

    emitter = TaskProgressEmitter(
        task_id=task_id,
        conversation_id=conversation_id,
        session_factory=async_session_factory,
        batch_size=4,
        max_flush_interval_seconds=99.0,
    )

    # 3 updates — below batch_size, nothing written yet
    for i in range(3):
        await emitter.update(percent=i / 4.0, message=f"r{i}")
    async with async_session_factory() as session:
        count_before = (
            await session.execute(
                select(func.count())
                .select_from(TaskProgress)
                .where(TaskProgress.task_id == task_id),
            )
        ).scalar_one()
    assert count_before == 0, "buffer should hold rows until full"

    # 4th update — batch fills, all 4 flush together
    await emitter.update(percent=0.75, message="r3")
    async with async_session_factory() as session:
        count_after = (
            await session.execute(
                select(func.count())
                .select_from(TaskProgress)
                .where(TaskProgress.task_id == task_id),
            )
        ).scalar_one()
    assert count_after == 4


@pytest.mark.asyncio
async def test_aclose_flushes_residual(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id, conversation_id, task_id = uuid4(), uuid4(), uuid4()
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
        await session.flush()
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="t",
                status="running",
                args={},
                estimated_duration_seconds=30,
            )
        )
        await session.commit()

    emitter = TaskProgressEmitter(
        task_id=task_id,
        conversation_id=conversation_id,
        session_factory=async_session_factory,
        batch_size=8,
        max_flush_interval_seconds=99.0,
    )
    await emitter.update(percent=0.5, message="only one")
    await emitter.aclose()
    async with async_session_factory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(TaskProgress)
                .where(TaskProgress.task_id == task_id),
            )
        ).scalar_one()
    assert count == 1
