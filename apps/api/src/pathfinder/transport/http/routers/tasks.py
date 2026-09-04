"""HTTP endpoint for the durable task list of a conversation."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from pathfinder.platform.security import get_current_user
from pathfinder.services.tasks.queries import (
    latest_progress_by_task,
    list_task_rows,
)
from pathfinder.transport.http.schemas.tasks import TaskListItem, TaskListResponse

router = APIRouter(prefix="/api/v1/conversations", tags=["tasks"])


@router.get("/{conversation_id}/tasks", response_model=TaskListResponse)
async def list_tasks(
    conversation_id: UUID,
    user_id: Annotated[UUID, Depends(get_current_user)],
    status_in: Annotated[
        str | None,
        Query(
            alias="status",
            description=(
                "Comma-separated status filter "
                "(pending, running, resuming, complete, failed)"
            ),
        ),
    ] = None,
) -> TaskListResponse:
    """Return durable tasks for a conversation, newest first."""
    statuses: set[str] | None = None
    if status_in:
        statuses = {s.strip() for s in status_in.split(",") if s.strip()}
    tasks = await list_task_rows(
        conversation_id=conversation_id,
        user_id=user_id,
        statuses=statuses,
    )
    latest = await latest_progress_by_task([t.id for t in tasks])
    items = [
        TaskListItem(
            task_id=task.id,
            tool_name=task.tool_name,
            status=task.status,
            estimated_duration_seconds=task.estimated_duration_seconds,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            latest_percent=latest[task.id].percent if task.id in latest else None,
            latest_message=latest[task.id].message if task.id in latest else None,
            error=task.error,
        )
        for task in tasks
    ]
    return TaskListResponse(tasks=items)
