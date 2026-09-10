"""A durable task reports itself on the thread, not only on its own channel.

The worker writes ``data-task-progress`` and ``data-task-completed`` into
``conversation_events`` so a reader of the main stream learns the whole
lifecycle. Progress is coalesced: the first update, a five-point advance, ten
seconds of silence, and always the last update.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.event_stream import fetch_chunks_after, iter_sse
from assistant_core.conversation.event_writer import ChatEventWriter
from assistant_core.graph.stream_events import background_task_started_event
from assistant_core.persistence.models import Conversation, ConversationEvent
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
from pydantic_ai.ui.vercel_ai.response_types import DoneChunk
from sqlalchemy import select

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID

TOOL_NAME = "test_thread_progress"


@pytest.fixture(autouse=True)
def _clean_tool_registry() -> Iterator[None]:
    with empty_durable_tools():
        yield


async def _seed(user_id: UUID, conversation_id: UUID) -> None:
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
            ),
        )
        await session.commit()


async def _thread_rows(conversation_id: UUID) -> list[ConversationEvent]:
    async with async_session_factory() as session:
        rows = (
            await session.scalars(
                select(ConversationEvent)
                .where(ConversationEvent.conversation_id == conversation_id)
                .order_by(ConversationEvent.id),
            )
        ).all()
        return list(rows)


def _of_type(rows: list[ConversationEvent], kind: str) -> list[dict[str, Any]]:
    return [row.chunk for row in rows if row.chunk.get("type") == kind]


async def _run(
    *,
    tool_name: str,
    conversation_id: UUID,
    user_id: UUID,
    args: dict[str, Any] | None = None,
) -> UUID:
    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=tool_name,
            args={"args": [], "kwargs": args or {}},
            tool_call_id=f"call_{tool_name}",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )
    await run_durable_task(
        tool_name=tool_name,
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": args or {}},
    )
    return task_id


def _register_ramp(steps: int) -> None:
    """A tool that reports ``steps`` updates, one percentage point apart."""

    async def _impl(
        *,
        context: Any,
        task_id: UUID,
        progress: TaskProgressEmitter,
        memory_store: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context, task_id, memory_store, kwargs
        for step in range(steps):
            await progress.update(percent=step / 100, message=f"step {step}")
        return {"steps": steps}

    register_durable_impl(
        declare_durable_tool(tool_name=TOOL_NAME, estimated_duration_seconds=10),
        _impl,
    )


@pytest.mark.asyncio
async def test_progress_reaches_the_thread_coalesced(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)
    _register_ramp(20)

    task_id = await _run(
        tool_name=TOOL_NAME,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    rows = await _thread_rows(conversation_id)
    progress = _of_type(rows, "data-task-progress")
    percents = [chunk["data"]["percent"] for chunk in progress]

    assert percents == [0.0, 0.05, 0.1, 0.15, 0.19]
    assert all(chunk["id"] == str(task_id) for chunk in progress)
    assert all(chunk["data"]["taskId"] == str(task_id) for chunk in progress)


@pytest.mark.asyncio
async def test_progress_rows_are_untagged_so_the_chat_stream_carries_them(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)
    _register_ramp(3)

    await _run(
        tool_name=TOOL_NAME,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    rows = await _thread_rows(conversation_id)
    _, chunks = await fetch_chunks_after(conversation_id, 0)

    assert [row.task_id for row in rows] == [None] * len(rows)
    assert [row.turn_id for row in rows] == [None] * len(rows)
    assert [chunk["type"] for chunk in chunks] == [row.chunk["type"] for row in rows]


@pytest.mark.asyncio
async def test_the_thread_replays_started_progress_completed_in_order(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)
    _register_ramp(3)

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=TOOL_NAME,
            args={"args": [], "kwargs": {}},
            tool_call_id="call_lifecycle_in_order",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )
    await ChatEventWriter(conversation_id=conversation_id, turn_id=uuid4()).write(
        background_task_started_event(
            task_id=task_id,
            tool_name=TOOL_NAME,
            estimated_duration_seconds=10,
        ).model_dump(by_alias=True, mode="json", exclude_none=True),
    )
    await run_durable_task(
        tool_name=TOOL_NAME,
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": {}},
    )

    _, chunks = await fetch_chunks_after(conversation_id, 0)
    lifecycle = [
        chunk["type"]
        for chunk in chunks
        if str(chunk["type"]).startswith(("data-task", "data-background-task"))
    ]

    assert lifecycle[0] == "data-background-task-started"
    assert lifecycle[-1] == "data-task-completed"
    assert set(lifecycle[1:-1]) == {"data-task-progress"}


def _framed(frame: str) -> tuple[int, str]:
    """Read one event frame as ``(cursor, payload)``."""
    id_line, data_line = frame.rstrip("\n").split("\n")
    return int(id_line.removeprefix("id: ")), data_line.removeprefix("data: ")


@pytest.mark.asyncio
async def test_a_tail_from_the_turn_terminator_frames_the_gap(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)
    _register_ramp(3)

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=TOOL_NAME,
            args={"args": [], "kwargs": {}},
            tool_call_id="call_gap_after_the_terminator",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )
    writer = ChatEventWriter(conversation_id=conversation_id, turn_id=uuid4())
    terminator = await writer.write(
        DoneChunk().model_dump(by_alias=True, mode="json", exclude_none=True),
    )
    await run_durable_task(
        tool_name=TOOL_NAME,
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": {}},
    )
    # The tail stops at the next terminator, which the resumed turn writes.
    await writer.write(
        DoneChunk().model_dump(by_alias=True, mode="json", exclude_none=True),
    )

    frames = [
        _framed(frame)
        async for frame in iter_sse(
            conversation_id=conversation_id,
            after=terminator,
        )
    ]
    cursors = [cursor for cursor, _ in frames]
    types = [
        "[DONE]" if payload == "[DONE]" else str(json.loads(payload)["type"])
        for _, payload in frames
    ]

    assert types[-2:] == ["data-task-completed", "[DONE]"]
    assert set(types[:-2]) == {"data-task-progress"}
    assert cursors == sorted(set(cursors))
    assert cursors[0] > terminator


@pytest.mark.asyncio
async def test_a_failed_tool_reports_its_failure_on_the_thread(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)

    async def _boom(
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
        declare_durable_tool(tool_name=TOOL_NAME, estimated_duration_seconds=10),
        _boom,
    )

    task_id = await _run(
        tool_name=TOOL_NAME,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    completed = _of_type(await _thread_rows(conversation_id), "data-task-completed")

    assert len(completed) == 1
    assert completed[0]["data"] == {
        "taskId": str(task_id),
        "status": "failed",
        "error": "kaboom",
    }


@pytest.mark.asyncio
async def test_an_unknown_tool_reports_its_failure_on_the_thread(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)

    task_id = await _run(
        tool_name="no_such_durable_tool",
        conversation_id=conversation_id,
        user_id=user_id,
    )

    completed = _of_type(await _thread_rows(conversation_id), "data-task-completed")

    assert len(completed) == 1
    assert completed[0]["data"]["taskId"] == str(task_id)
    assert completed[0]["data"]["status"] == "failed"


@pytest.mark.asyncio
async def test_a_task_that_reports_nothing_still_completes_on_the_thread(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)

    async def _silent(
        *,
        context: Any,
        task_id: UUID,
        progress: TaskProgressEmitter,
        memory_store: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context, task_id, progress, memory_store, kwargs
        return {"ok": True}

    register_durable_impl(
        declare_durable_tool(tool_name=TOOL_NAME, estimated_duration_seconds=10),
        _silent,
    )

    task_id = await _run(
        tool_name=TOOL_NAME,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    rows = await _thread_rows(conversation_id)

    assert _of_type(rows, "data-task-progress") == []
    assert _of_type(rows, "data-task-completed") == [
        {
            "type": "data-task-completed",
            "data": {"taskId": str(task_id), "status": "success"},
        },
    ]


@pytest.mark.asyncio
async def test_each_scoped_lane_leaves_a_part_of_its_own(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)

    async def _fanout(
        *,
        context: Any,
        task_id: UUID,
        progress: TaskProgressEmitter,
        memory_store: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del context, task_id, memory_store, kwargs
        for variant in ("a", "b", "c"):
            child = progress.scoped(variantId=variant)
            for step in range(3):
                await child.update(percent=step / 100, message=f"{variant} {step}")
            await child.aclose()
        return {"ok": True}

    register_durable_impl(
        declare_durable_tool(tool_name=TOOL_NAME, estimated_duration_seconds=10),
        _fanout,
    )

    task_id = await _run(
        tool_name=TOOL_NAME,
        conversation_id=conversation_id,
        user_id=user_id,
    )

    progress = _of_type(await _thread_rows(conversation_id), "data-task-progress")

    assert [chunk["data"]["message"] for chunk in progress] == [
        "a 0",
        "a 2",
        "b 0",
        "b 2",
        "c 0",
        "c 2",
    ]
    assert [chunk["id"] for chunk in progress] == [
        f"{task_id}:a",
        f"{task_id}:a",
        f"{task_id}:b",
        f"{task_id}:b",
        f"{task_id}:c",
        f"{task_id}:c",
    ]
    assert {chunk["id"] for chunk in progress} == {
        f"{task_id}:{variant}" for variant in "abc"
    }
