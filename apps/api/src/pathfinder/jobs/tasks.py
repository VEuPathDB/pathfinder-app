"""Procrastinate task registrations for the Pathfinder worker.

All tasks register on import via the ``@procrastinate_app.task`` decorator.
``ensure_registered`` is a no-op call-site marker used by the bootstrap
path so importing this module is not flagged as an unused import.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from assistant_core.tasks.maintenance import release_stalled_jobs
from assistant_core.tasks.names import (
    CHAT_TURN_QUEUE,
    CHAT_TURN_TASK,
    DEFAULT_QUEUE,
    MAINTENANCE_QUEUE,
    RELEASE_STALLED_JOBS_TASK,
)
from veupathdb_mcp.embeddings import prune_orphan_vectors

from pathfinder.jobs.app import procrastinate_app
from pathfinder.jobs.auth_context import attach_application
from pathfinder.jobs.impls.chat_turn_impl import run_chat_turn
from pathfinder.services.eval_data.extraction import extract_eval_candidates

# A vector nothing names is kept for a week: a rebuilt index reuses it.
ORPHAN_VECTOR_GRACE = timedelta(days=7)


def ensure_registered() -> None:
    """No-op that keeps the module-import side effects live.

    The real work is the ``@procrastinate_app.task`` decorators below - those
    run at import time. This function exists so callers that need to
    guarantee tasks are registered (the worker bootstrap path) can reference
    the module without relying on unused-import semantics.
    """


@procrastinate_app.task(queue=DEFAULT_QUEUE, name="echo")
async def echo_task(message: str) -> str:
    """Smoke task for worker/app bring-up tests."""
    return message


@procrastinate_app.task(queue=CHAT_TURN_QUEUE, name=CHAT_TURN_TASK)
async def run_chat_turn_job(payload: dict[str, Any]) -> None:
    await run_chat_turn(payload)


# The sweep settles work no job lock protects, so the lock keeps two runs of
# it apart.
@procrastinate_app.periodic(cron="* * * * *")
@procrastinate_app.task(
    queue=MAINTENANCE_QUEUE,
    name=RELEASE_STALLED_JOBS_TASK,
    lock="maintenance:release-stalled-jobs",
)
async def release_stalled_jobs_job(timestamp: int) -> None:
    del timestamp
    async with attach_application():
        await release_stalled_jobs()


@procrastinate_app.periodic(cron="41 4 * * *")
@procrastinate_app.task(
    queue=MAINTENANCE_QUEUE, name="maintenance:prune_orphan_vectors"
)
async def prune_orphan_vectors_job(timestamp: int) -> None:
    del timestamp
    async with attach_application():
        await prune_orphan_vectors(ORPHAN_VECTOR_GRACE)


@procrastinate_app.periodic(cron="17 3 * * *")
@procrastinate_app.task(
    queue=MAINTENANCE_QUEUE, name="maintenance:extract_eval_candidates"
)
async def extract_eval_candidates_job(timestamp: int) -> None:
    del timestamp
    async with attach_application():
        await extract_eval_candidates()
