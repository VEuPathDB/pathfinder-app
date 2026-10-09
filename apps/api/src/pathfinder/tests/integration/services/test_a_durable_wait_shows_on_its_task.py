from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    TaskProgressRow,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.progress import TaskProgressEmitter
from sqlalchemy import func, select
from veupathdb.wdk import SearchRequest
from veupathdb_mcp.search_line import search_line_gate

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.search_waits import told_on_progress

_SNP = SearchRequest(
    site_id="plasmodb", kind="report", search_names=frozenset({"GenesByNgsSnps"})
)


async def _a_running_task() -> tuple[UUID, UUID]:
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
                tool_name="separate_controls",
                status="running",
                args={},
                estimated_duration_seconds=10,
            )
        )
        await session.commit()
    return task_id, conversation_id


async def _rows(task_id: UUID) -> list[tuple[float, str]]:
    async with async_session_factory() as session:
        found = await session.execute(
            select(TaskProgressRow.percent, TaskProgressRow.message)
            .where(TaskProgressRow.task_id == task_id)
            .order_by(TaskProgressRow.id)
        )
        return [(row.percent, row.message) for row in found]


class _LineUntilTold:
    def __init__(self, task_id: UUID) -> None:
        self.task_id = task_id

    @asynccontextmanager
    async def hold(self, site_id: str) -> AsyncIterator[None]:
        del site_id
        async with asyncio.timeout(10):
            while True:
                async with async_session_factory() as session:
                    told = await session.scalar(
                        select(func.count())
                        .select_from(TaskProgressRow)
                        .where(TaskProgressRow.task_id == self.task_id)
                        .where(TaskProgressRow.message.startswith("Waiting"))
                    )
                if told:
                    break
                await asyncio.sleep(0.01)
        yield


@pytest.mark.usefixtures("db_cleaner", "patch_app_db_engine")
async def test_a_durable_body_that_waits_for_the_line_says_so_on_its_task() -> None:
    task_id, conversation_id = await _a_running_task()
    gate = search_line_gate(_LineUntilTold(task_id), notice_seconds=0.0)

    async def body(*, progress: TaskProgressEmitter, **_: Any) -> str:
        await progress.update(percent=0.4, message="Measuring candidates")
        async with gate(_SNP):
            return "measured"

    answer = await told_on_progress(body)(
        progress=TaskProgressEmitter(
            task_id=task_id,
            conversation_id=conversation_id,
            session_factory=async_session_factory,
        )
    )

    assert answer == "measured"
    assert await _rows(task_id) == [
        (0.4, "Measuring candidates"),
        (0.4, "Waiting for PlasmoDB"),
        (0.4, "Measuring candidates"),
    ]
