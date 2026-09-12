from __future__ import annotations

from collections.abc import Iterator

import pytest
from assistant_core.tasks.declaration import declared_durable_tools
from assistant_core.tasks.runner import register_durable_jobs

from pathfinder.jobs.app import DURABLE_TASK_QUEUE, procrastinate_app
from pathfinder.jobs.impls import register_all_tools

_TASK_ID = "00000000-0000-0000-0000-000000000001"
_THREAD_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(scope="module", autouse=True)
def durable_jobs() -> Iterator[None]:
    """Register the jobs the worker registers, and leave the app as it was."""
    register_all_tools()
    before = dict(procrastinate_app.tasks)
    register_durable_jobs(procrastinate_app)
    try:
        yield
    finally:
        procrastinate_app.tasks.clear()
        procrastinate_app.tasks.update(before)


def test_durable_tasks_registered_on_verification_queue() -> None:
    """One job per declaration, all on the queue a long tool runs on."""
    names = {tool.job_name for tool in declared_durable_tools()}

    assert names == {
        "durable:run_control_tests_on_step",
        "durable:optimize_search_parameters",
        "durable:geneset_enrichment",
        "durable:run_eda_compute",
    }
    assert names <= set(procrastinate_app.tasks)
    assert {procrastinate_app.tasks[name].queue for name in names} == {
        DURABLE_TASK_QUEUE,
    }


async def test_durable_tasks_can_be_deferred(
    db_cleaner: None, patch_app_db_engine: None
) -> None:
    del db_cleaner, patch_app_db_engine
    async with procrastinate_app.open_async():
        job_ids = [
            await procrastinate_app.tasks[tool.job_name].defer_async(
                task_id=_TASK_ID,
                thread_id=_THREAD_ID,
                args={"args": [], "kwargs": {}},
            )
            for tool in declared_durable_tools()
        ]
    assert len(job_ids) == 4
    assert all(job_id > 0 for job_id in job_ids)
