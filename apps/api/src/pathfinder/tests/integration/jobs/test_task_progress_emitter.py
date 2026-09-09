from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select

from pathfinder.jobs.progress import TaskProgressEmitter
from pathfinder.persistence.models import BackgroundTask, TaskProgress, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.mark.asyncio
async def test_emitter_writes_progress_rows_in_order(
    db_cleaner: None, patch_app_db_engine: None
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    conversation_id = uuid4()
    task_id = uuid4()
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
        await session.flush()
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="t",
                status="running",
                args={},
                estimated_duration_seconds=10,
            )
        )
        await session.commit()

    emitter = TaskProgressEmitter(
        task_id=task_id,
        conversation_id=conversation_id,
        session_factory=async_session_factory,
    )
    await emitter.update(percent=0.25, message="starting", data=None)
    await emitter.update(percent=0.5, message="halfway", data={"step": "check"})
    await emitter.update(percent=1.0, message="done", data=None)

    async with async_session_factory() as session:
        result = await session.execute(
            select(TaskProgress)
            .where(TaskProgress.task_id == task_id)
            .order_by(TaskProgress.id)
        )
        rows = list(result.scalars().all())

    assert len(rows) == 3
    assert rows[0].message == "starting"
    assert rows[0].percent == 0.25
    assert rows[1].message == "halfway"
    assert rows[1].data == {"step": "check"}
    assert rows[2].message == "done"
    assert rows[2].percent == 1.0
