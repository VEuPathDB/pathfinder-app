"""Entry point for the Pathfinder Procrastinate worker.

Run with ``python -m pathfinder.jobs.worker``. ``register_all_tools`` imports
``tasks`` (so ``@procrastinate_app.task`` decorators register the task names)
and binds every durable body before the worker starts pulling jobs. The
runtime's own redaction is installed by ``setup_logging``, so the durable
job line is scrubbed whichever order the two calls take.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from assistant_core.mcp.admission import install_admitted_sources
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import setup_logging
from assistant_core.registry import install_assistant_registry
from assistant_core.tasks.completion_turn import install_completion_turn
from assistant_core.tasks.heartbeat import HeartbeatThread, postgres_beat_writer
from assistant_core.tasks.job_context import install_durable_job_context
from assistant_core.tasks.names import WORKER_QUEUES
from assistant_core.tasks.runner import install_worker_context, register_durable_jobs
from procrastinate.worker import Worker
from veupathdb_mcp.embeddings.db import use_embedding_session_factory

from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.jobs.app import procrastinate_app
from pathfinder.jobs.completion import open_completion_turn
from pathfinder.jobs.impls import register_all_tools
from pathfinder.jobs.job_context import WdkJobContext
from pathfinder.jobs.logging_filters import install_procrastinate_redaction
from pathfinder.jobs.runtime import build_worker_context
from pathfinder.platform.config import get_settings
from pathfinder.platform.tool_sources import admitted_tool_sources


class _RunningWorker(Protocol):
    """The procrastinate worker surface this entry point drives."""

    worker_id: int | None

    async def run(self) -> None: ...


async def amain() -> None:
    setup_logging()
    install_procrastinate_redaction()
    # The index shares this process's pool instead of opening a second one.
    use_embedding_session_factory(async_session_factory)
    logging.getLogger(__name__).info("Pathfinder worker starting")
    # Turns run here, so this is the process where a declaration resolves.
    install_admitted_sources(admitted_tool_sources())
    register_all_tools()
    install_durable_job_context(WdkJobContext())
    install_worker_context(build_worker_context)
    install_completion_turn(open_completion_turn)
    install_assistant_registry(get_assistant_registry())
    register_durable_jobs(procrastinate_app)
    settings = get_settings()
    procrastinate_app.perform_import_paths()
    # The worker is built here rather than through run_worker_async so the
    # heartbeat thread can read the worker id procrastinate registers.
    worker: _RunningWorker = Worker(
        app=procrastinate_app,
        queues=list(WORKER_QUEUES),
        concurrency=settings.worker_concurrency,
        install_signal_handlers=True,
        update_heartbeat_interval=settings.worker_heartbeat_interval_seconds,
    )
    heartbeat = HeartbeatThread(
        worker_id=lambda: worker.worker_id,
        write=postgres_beat_writer(settings.database_url),
        interval_seconds=settings.worker_heartbeat_interval_seconds,
    )
    async with procrastinate_app.open_async():
        heartbeat.start()
        try:
            await worker.run()
        finally:
            heartbeat.stop()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
