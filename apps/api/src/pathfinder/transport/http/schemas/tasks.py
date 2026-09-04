from __future__ import annotations

from datetime import datetime
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel


class TaskListItem(CamelModel):
    task_id: UUID
    tool_name: str
    status: str
    estimated_duration_seconds: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    latest_percent: float | None = None
    latest_message: str | None = None
    error: str | None = None


class TaskListResponse(CamelModel):
    tasks: list[TaskListItem]
