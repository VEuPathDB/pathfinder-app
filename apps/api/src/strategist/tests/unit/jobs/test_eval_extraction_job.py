"""The extraction pass is a scheduled maintenance task."""

from __future__ import annotations

from strategist.jobs.app import procrastinate_app
from strategist.jobs.tasks import ensure_registered

_TASK_NAME = "maintenance:extract_eval_candidates"


def test_extraction_runs_daily_on_the_maintenance_queue() -> None:
    ensure_registered()
    task = procrastinate_app.tasks[_TASK_NAME]

    assert task.queue == "maintenance"
    registered = [
        periodic
        for periodic in procrastinate_app.periodic_registry.periodic_tasks.values()
        if periodic.task.name == _TASK_NAME
    ]
    assert len(registered) == 1
    assert registered[0].cron == "17 3 * * *"
