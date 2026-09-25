"""A durable task's status on the wire is one of the statuses the runtime writes."""

from typing import get_args

from assistant_core.persistence.repositories.background_tasks import (
    ACTIVE_TASK_STATES,
    REPORTED_TASK_STATES,
)

from pathfinder.transport.http.schemas.tasks import TaskListItem, TaskStatus


def test_the_status_names_every_state_the_runtime_writes() -> None:
    assert set(get_args(TaskStatus)) == {*ACTIVE_TASK_STATES, *REPORTED_TASK_STATES}


def test_the_published_status_is_an_enum() -> None:
    status = TaskListItem.model_json_schema(by_alias=True)["properties"]["status"]

    assert status["enum"] == [
        "pending",
        "running",
        "result_ready",
        "resuming",
        "complete",
        "failed",
    ]
