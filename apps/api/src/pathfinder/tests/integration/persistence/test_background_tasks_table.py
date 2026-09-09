from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform.db import async_session_factory
from sqlalchemy import select

from pathfinder.persistence.models import BackgroundTask, TaskProgress, User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.mark.asyncio
async def test_background_tasks_roundtrip(
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
                tool_name="test_tool",
                status="pending",
                args={"kwargs": {}},
                estimated_duration_seconds=60,
            )
        )
        await session.flush()
        session.add(
            TaskProgress(
                task_id=task_id,
                percent=0.5,
                message="halfway",
                data=None,
            )
        )
        session.add(
            ConversationEvent(
                conversation_id=conversation_id,
                task_id=task_id,
                chunk={"type": "test"},
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        task = (
            await session.execute(
                select(BackgroundTask).where(BackgroundTask.id == task_id)
            )
        ).scalar_one()
        assert task.status == "pending"
        assert task.tool_name == "test_tool"
        assert task.estimated_duration_seconds == 60

        progress = (
            await session.execute(
                select(TaskProgress).where(TaskProgress.task_id == task_id)
            )
        ).scalar_one()
        assert progress.percent == 0.5
        assert progress.message == "halfway"

        event = (
            await session.execute(
                select(ConversationEvent).where(
                    ConversationEvent.conversation_id == conversation_id
                )
            )
        ).scalar_one()
        assert event.chunk == {"type": "test"}
        assert event.task_id == task_id
