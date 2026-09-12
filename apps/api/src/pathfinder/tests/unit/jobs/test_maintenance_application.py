"""A periodic maintenance job writes rows as this application."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest
from assistant_core.platform.context import calling_application

from pathfinder.jobs import tasks
from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID


@pytest.mark.parametrize(
    ("job", "target"),
    [
        (tasks.release_stalled_jobs_job, "release_stalled_jobs"),
        (tasks.prune_orphan_vectors_job, "prune_orphan_vectors"),
        (tasks.extract_eval_candidates_job, "extract_eval_candidates"),
    ],
)
async def test_a_maintenance_task_body_names_this_application(
    monkeypatch: pytest.MonkeyPatch,
    job: Callable[..., Awaitable[None]],
    target: str,
) -> None:
    """No request or thread names an application for a periodic job."""
    seen: list[str] = []

    async def _record(*args: object) -> None:
        del args
        seen.append(calling_application())

    monkeypatch.setattr(tasks, target, _record)

    await job(timestamp=0)

    assert seen == [PATHFINDER_APPLICATION_ID]


def test_the_stalled_job_sweep_runs_one_at_a_time() -> None:
    """The sweep settles work no job lock protects, so two runs never overlap."""
    assert tasks.release_stalled_jobs_job.lock == "maintenance:release-stalled-jobs"
