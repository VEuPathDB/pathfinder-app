from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from assistant_core.graph.turn_state import PendingApproval
from assistant_core.persistence.models import BackgroundTask
from assistant_core.platform import db
from assistant_core.tasks.chat_turn import defer_chat_turn
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text, update

from pathfinder.jobs.app import procrastinate_app


async def queue_turn(conversation_id: UUID, user_id: UUID) -> None:
    async with procrastinate_app.open_async():
        await defer_chat_turn(
            conversation_id=conversation_id,
            payload={
                "user_id": str(user_id),
                "turnId": str(uuid4()),
                "body": {"conversationId": str(conversation_id)},
            },
        )


async def set_turn_status(conversation_id: UUID, status: str) -> None:
    async with db.async_session_factory() as session:
        await session.execute(
            text("UPDATE procrastinate_jobs SET status = :status WHERE lock = :lock"),
            {"status": status, "lock": str(conversation_id)},
        )
        await session.commit()


async def put_pending_approval(
    saver: AsyncPostgresSaver,
    conversation_id: UUID,
    approval: PendingApproval | None,
) -> None:
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"pending_approval": approval}
    checkpoint["channel_versions"] = {
        "pending_approval": saver.get_next_version(None, None),
    }
    await saver.aput(
        {"configurable": {"thread_id": str(conversation_id), "checkpoint_ns": ""}},
        checkpoint,
        {},
        checkpoint["channel_versions"],
    )


async def start_task(conversation_id: UUID, user_id: UUID) -> UUID:
    task_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="run_eda_compute",
                status="running",
            ),
        )
        await session.commit()
    return task_id


async def finish_task(task_id: UUID) -> None:
    async with db.async_session_factory() as session:
        await session.execute(
            update(BackgroundTask)
            .where(BackgroundTask.id == task_id)
            .values(status="complete"),
        )
        await session.commit()


PROPOSAL = PendingApproval(
    phase="lead",
    tool_call_id="call-propose-1",
    tool_name="propose_changes",
)

Clear = Callable[[], Awaitable[None]]


async def make_busy(
    kind: str,
    *,
    saver: AsyncPostgresSaver,
    conversation_id: UUID,
    user_id: UUID,
) -> Clear:
    if kind in {"queued turn", "running turn"}:
        await queue_turn(conversation_id, user_id)
        if kind == "running turn":
            await set_turn_status(conversation_id, "doing")

        async def _finish_turn() -> None:
            await set_turn_status(conversation_id, "succeeded")

        return _finish_turn
    if kind == "pending approval":
        await put_pending_approval(saver, conversation_id, PROPOSAL)

        async def _answer() -> None:
            await put_pending_approval(saver, conversation_id, None)

        return _answer
    task_id = await start_task(conversation_id, user_id)

    async def _finish() -> None:
        await finish_task(task_id)

    return _finish
