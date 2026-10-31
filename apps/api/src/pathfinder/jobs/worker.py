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
from collections.abc import Iterable
from typing import Protocol

import procrastinate
from assistant_core.mcp.admission import install_admitted_sources
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import setup_logging
from assistant_core.platform.observability import shutdown_observability
from assistant_core.registry import install_assistant_registry
from assistant_core.tasks.app import worker_queues
from assistant_core.tasks.completion_turn import install_completion_turn
from assistant_core.tasks.heartbeat import HeartbeatThread, postgres_beat_writer
from assistant_core.tasks.job_context import install_durable_job_context
from assistant_core.tasks.runner import install_worker_context, register_durable_jobs
from procrastinate import signals
from procrastinate.worker import Worker
from veupathdb import set_observer
from veupathdb_mcp.embeddings import use_embedding_session_factory
from veupathdb_mcp.search_line import install_search_line
from veupathdb_mcp.strategy_line import install_strategy_line

from pathfinder.ai.capabilities.security import warm_up_screening
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.jobs.app import FINISHED_JOBS_DELETED, procrastinate_app
from pathfinder.jobs.completion import open_completion_turn
from pathfinder.jobs.impls import register_all_tools
from pathfinder.jobs.job_context import WdkJobContext
from pathfinder.jobs.logging_filters import install_procrastinate_redaction
from pathfinder.jobs.runtime import build_worker_context
from pathfinder.platform.config import Settings, get_settings
from pathfinder.platform.langfuse.client import shutdown_langfuse
from pathfinder.platform.metrics import PathfinderObserver, serve_metrics
from pathfinder.platform.model_catalog import install_catalog_prices
from pathfinder.platform.observability import setup_observability
from pathfinder.platform.tool_sources import admitted_tool_sources
from pathfinder.services.audit.lease_pool import close_audit_lease_engine
from pathfinder.services.audit.queue import AUDIT_QUEUE
from pathfinder.services.search_waits import runs_on_the_deployment_line

AUDIT_SHUTDOWN_SECONDS = 5.0
_CANNOT_SCREEN = "the injection judge did not build; this worker consumes no jobs"


class WorkerCannotScreenError(RuntimeError):
    """The worker cannot screen a tool result, so it refuses to start."""


def _build_the_injection_judge() -> None:
    """Build the judge before the worker pulls a job.

    Every tool result this process reads crosses the judge. A worker that
    cannot build it would withhold every result of every turn, so it stops
    instead. The api answers 503 for the same misconfiguration.
    """
    if not get_settings().input_screening_enabled:
        return
    try:
        warm_up_screening()
    except Exception as error:
        logging.getLogger(__name__).exception(
            "The injection judge did not build. Point INPUT_SCREENING_MODEL at a "
            "model this deployment can reach, or set "
            "INPUT_SCREENING_ENABLED=false to run without screening.",
        )
        raise WorkerCannotScreenError(_CANNOT_SCREEN) from error


class ServingWorker(Protocol):
    """The procrastinate worker surface this entry point drives."""

    worker_id: int | None
    queues: Iterable[str] | None
    concurrency: int
    install_signal_handlers: bool
    shutdown_graceful_timeout: float | None

    async def run(self) -> None: ...

    def stop(self) -> None: ...


def serving_workers(
    app: procrastinate.App, settings: Settings
) -> tuple[ServingWorker, ServingWorker]:
    turns = Worker(
        app=app,
        delete_jobs=FINISHED_JOBS_DELETED,
        queues=list(worker_queues()),
        concurrency=settings.worker_concurrency,
        install_signal_handlers=False,
        update_heartbeat_interval=settings.worker_heartbeat_interval_seconds,
    )
    audits = Worker(
        app=app,
        name="audit",
        delete_jobs=FINISHED_JOBS_DELETED,
        queues=[AUDIT_QUEUE],
        concurrency=settings.audit_concurrency,
        install_signal_handlers=False,
        shutdown_graceful_timeout=AUDIT_SHUTDOWN_SECONDS,
        update_heartbeat_interval=settings.worker_heartbeat_interval_seconds,
    )
    return turns, audits


def _stop(workers: tuple[ServingWorker, ...]) -> None:
    for worker in workers:
        worker.stop()


async def serve_workers(*workers: ServingWorker) -> None:
    with signals.on_stop(lambda: _stop(workers)):
        running = [asyncio.create_task(worker.run()) for worker in workers]
        done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
        _stop(workers)
        await asyncio.gather(*running, return_exceptions=True)
    for task in done:
        task.result()


def _heartbeat(worker: ServingWorker, settings: Settings) -> HeartbeatThread:
    return HeartbeatThread(
        worker_id=lambda: worker.worker_id,
        write=postgres_beat_writer(settings.database_url),
        interval_seconds=settings.worker_heartbeat_interval_seconds,
    )


async def amain() -> None:
    setup_logging()
    setup_observability(service_name="pathfinder-worker")
    install_procrastinate_redaction()
    install_catalog_prices()
    # The index shares this process's pool instead of opening a second one.
    use_embedding_session_factory(async_session_factory)
    logging.getLogger(__name__).info("Pathfinder worker starting")
    _build_the_injection_judge()
    # Turns run here, so this is the process where a declaration resolves.
    install_admitted_sources(admitted_tool_sources())
    register_all_tools()
    install_durable_job_context(WdkJobContext())
    install_worker_context(build_worker_context)
    install_completion_turn(open_completion_turn)
    install_assistant_registry(get_assistant_registry())
    register_durable_jobs(procrastinate_app)
    settings = get_settings()
    serve_metrics(settings.metrics_port, settings.metrics_addr)
    set_observer(PathfinderObserver())
    install_search_line(
        settings.database_url,
        runs_on_the_deployment_line,
        pool_size=settings.search_line_pool_size,
        max_overflow=settings.search_line_max_overflow,
        pool_timeout=settings.search_line_pool_timeout_seconds,
    )
    install_strategy_line(
        settings.database_url,
        pool_size=settings.strategy_line_pool_size,
        max_overflow=settings.strategy_line_max_overflow,
        pool_timeout=settings.strategy_line_pool_timeout_seconds,
    )
    procrastinate_app.perform_import_paths()
    # The workers are built here rather than through run_worker_async so each
    # heartbeat thread can read the worker id procrastinate registers.
    turns, audits = serving_workers(procrastinate_app, settings)
    heartbeats = [_heartbeat(worker, settings) for worker in (turns, audits)]
    async with procrastinate_app.open_async():
        for heartbeat in heartbeats:
            heartbeat.start()
        try:
            await serve_workers(turns, audits)
        finally:
            for heartbeat in heartbeats:
                heartbeat.stop()
            await close_audit_lease_engine()
            shutdown_observability()
            shutdown_langfuse()


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
