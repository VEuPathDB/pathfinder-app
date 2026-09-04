"""Read queries for durable tasks + their progress rows.

Owns all ``background_tasks`` / ``task_progress`` access so the transport
task router never imports persistence.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import calling_application
from assistant_core.platform.db import async_session_factory
from sqlalchemy import Select, select

from pathfinder.persistence.models import BackgroundTask, TaskProgress


@dataclass(frozen=True)
class TaskRow:
    id: UUID
    tool_name: str
    status: str
    estimated_duration_seconds: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class ProgressRow:
    percent: float
    message: str


def _to_task_row(t: BackgroundTask) -> TaskRow:
    return TaskRow(
        id=t.id,
        tool_name=t.tool_name,
        status=t.status,
        estimated_duration_seconds=t.estimated_duration_seconds,
        created_at=t.created_at,
        started_at=t.started_at,
        completed_at=t.completed_at,
        error=t.error,
    )


def _to_progress_row(p: TaskProgress) -> ProgressRow:
    return ProgressRow(percent=p.percent, message=p.message)


def _scoped_tasks(
    conversation_id: UUID, user_id: UUID
) -> Select[tuple[BackgroundTask]]:
    """Tasks of one conversation, which the user holds under this application."""
    return (
        select(BackgroundTask)
        .join(Conversation, BackgroundTask.conversation_id == Conversation.id)
        .where(
            BackgroundTask.conversation_id == conversation_id,
            BackgroundTask.user_id == user_id,
            Conversation.application_id == calling_application(),
        )
    )


async def list_task_rows(
    *,
    conversation_id: UUID,
    user_id: UUID,
    statuses: set[str] | None,
) -> list[TaskRow]:
    async with async_session_factory() as session:
        query = _scoped_tasks(conversation_id, user_id).order_by(
            BackgroundTask.created_at.desc(),
        )
        if statuses:
            query = query.where(BackgroundTask.status.in_(statuses))
        rows = (await session.execute(query)).scalars().all()
    return [_to_task_row(t) for t in rows]


async def latest_progress_by_task(task_ids: list[UUID]) -> dict[UUID, ProgressRow]:
    if not task_ids:
        return {}
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(TaskProgress)
                    .where(TaskProgress.task_id.in_(task_ids))
                    .order_by(TaskProgress.id.desc()),
                )
            )
            .scalars()
            .all()
        )
    latest: dict[UUID, ProgressRow] = {}
    for row in rows:
        latest.setdefault(row.task_id, _to_progress_row(row))
    return latest
