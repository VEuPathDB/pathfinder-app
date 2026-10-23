from __future__ import annotations

import logging
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
from assistant_core.tasks.runner import run_durable_task

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.tests._support.rendered_logs import rendered_logs

_TOOL = "log_probe"
_KEYS = ("conversation_id", "user_id", "site_id", "task_id", "tool_name")


@pytest.fixture(autouse=True)
def _own_registry() -> Iterator[None]:
    with empty_durable_tools():
        yield


async def _probe(**kwargs: Any) -> dict[str, str]:
    del kwargs
    logging.getLogger("veupathdb.wdk").warning("body line")
    return {}


async def _queued_task() -> tuple[UUID, UUID, UUID]:
    user_id, conversation_id = uuid4(), uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="toxodb",
                name="",
            )
        )
        await session.commit()
    task_id = await BackgroundTaskRepository(
        session_factory=async_session_factory
    ).create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=_TOOL,
            args={"args": [], "kwargs": {}},
            tool_call_id="call_log_probe",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )
    return user_id, conversation_id, task_id


@pytest.mark.usefixtures("db_cleaner", "patch_app_db_engine", "worker_seams")
async def test_a_line_a_body_writes_names_the_task_and_its_owner() -> None:
    register_durable_impl(
        declare_durable_tool(tool_name=_TOOL, estimated_duration_seconds=10), _probe
    )
    user_id, conversation_id, task_id = await _queued_task()

    with rendered_logs() as logs:
        await run_durable_task(
            tool_name=_TOOL,
            task_id=str(task_id),
            thread_id=str(conversation_id),
            args={"args": [], "kwargs": {}},
        )
        logging.getLogger("veupathdb.wdk").warning("after the task")

    line = logs.line("body line")
    assert {key: line[key] for key in _KEYS} == {
        "conversation_id": str(conversation_id),
        "user_id": str(user_id),
        "site_id": "toxodb",
        "task_id": str(task_id),
        "tool_name": _TOOL,
    }
    assert set(_KEYS) & set(logs.line("after the task")) == set()
