"""Stranded audit runs are queued again by a periodic job on the maintenance queue."""

from __future__ import annotations

from pathfinder.jobs import tasks
from pathfinder.jobs.app import procrastinate_app

_TASK_NAME = "maintenance:resume_stranded_audits"


def test_the_resume_pass_runs_every_five_minutes_on_the_maintenance_queue() -> None:
    task = procrastinate_app.tasks[_TASK_NAME]
    registered = [
        periodic.cron
        for periodic in procrastinate_app.periodic_registry.periodic_tasks.values()
        if periodic.task.name == _TASK_NAME
    ]

    assert task.queue == "maintenance"
    assert registered == [tasks.RESUME_STRANDED_AUDITS_CRON]
    assert tasks.RESUME_STRANDED_AUDITS_CRON == "*/5 * * * *"
