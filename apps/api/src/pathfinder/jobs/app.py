from __future__ import annotations

import procrastinate
from assistant_core.conversation.checkpointer import to_psycopg_url
from assistant_core.tasks.app import install_task_app
from procrastinate.jobs import DeleteJobCondition

from pathfinder.platform.config import get_settings

# The queue this deployment runs its durable work on. Every process of one
# deployment names it, so a deferred job reaches a worker that consumes it.
DURABLE_TASK_QUEUE = "verification"

FINISHED_JOBS_DELETED = DeleteJobCondition.ALWAYS


def _build_connector() -> procrastinate.PsycopgConnector:
    """Build a PsycopgConnector pointing at the app's Postgres database."""
    settings = get_settings()
    return procrastinate.PsycopgConnector(
        conninfo=to_psycopg_url(settings.database_url),
        min_size=settings.job_queue_pool_min_size,
        max_size=settings.job_queue_pool_max_size,
    )


procrastinate_app: procrastinate.App = procrastinate.App(
    connector=_build_connector(),
    worker_defaults={"delete_jobs": FINISHED_JOBS_DELETED},
)

# The runtime defers durable jobs onto this application's queue.
install_task_app(procrastinate_app, durable_queue=DURABLE_TASK_QUEUE)
