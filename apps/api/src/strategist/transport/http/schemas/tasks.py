from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel

TaskStatus = Literal[
    "pending", "running", "result_ready", "resuming", "complete", "failed"
]
"""Every status the runtime writes on a durable task row."""


class TaskListItem(CamelModel):
    task_id: UUID
    tool_name: str
    status: TaskStatus
    estimated_duration_seconds: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    latest_percent: float | None = None
    latest_message: str | None = None
    error: str | None = None


class TaskListResponse(CamelModel):
    tasks: list[TaskListItem]
