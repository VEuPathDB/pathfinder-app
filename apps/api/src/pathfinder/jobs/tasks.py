"""Procrastinate task registrations for the Pathfinder worker.

All tasks register on import via the ``@procrastinate_app.task`` decorator.
``ensure_registered`` is a no-op call-site marker used by the bootstrap
path so importing this module is not flagged as an unused import.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from veupathdb_mcp.embeddings.record_manager import prune_orphan_vectors

from pathfinder.jobs.app import procrastinate_app
from pathfinder.jobs.impls.chat_turn_impl import run_chat_turn
from pathfinder.jobs.maintenance import release_stalled_jobs
from pathfinder.jobs.runner import run_durable_task
from pathfinder.services.eval_data.extraction import extract_eval_candidates

# A vector nothing names is kept for a week: a rebuilt index reuses it.
ORPHAN_VECTOR_GRACE = timedelta(days=7)


def ensure_registered() -> None:
    """No-op that keeps the module-import side effects live.

    The real work is the ``@procrastinate_app.task`` decorators below — those
    run at import time. This function exists so callers that need to
    guarantee tasks are registered (the worker bootstrap path) can reference
    the module without relying on unused-import semantics.
    """


@procrastinate_app.task(queue="default", name="echo")
async def echo_task(message: str) -> str:
    """Smoke task for worker/app bring-up tests."""
    return message


@procrastinate_app.task(queue="verification", name="durable:run_control_tests_on_step")
async def run_control_tests_on_step_job(
    task_id: str,
    thread_id: str,
    args: dict[str, Any],
    veupathdb_auth_token: str | None = None,
    capture_dir: str | None = None,
) -> None:
    await run_durable_task(
        tool_name="run_control_tests_on_step",
        task_id=task_id,
        thread_id=thread_id,
        args=args,
        veupathdb_auth_token=veupathdb_auth_token,
        capture_dir=capture_dir,
    )


@procrastinate_app.task(queue="verification", name="durable:optimize_search_parameters")
async def optimize_search_parameters_job(
    task_id: str,
    thread_id: str,
    args: dict[str, Any],
    veupathdb_auth_token: str | None = None,
    capture_dir: str | None = None,
) -> None:
    await run_durable_task(
        tool_name="optimize_search_parameters",
        task_id=task_id,
        thread_id=thread_id,
        args=args,
        veupathdb_auth_token=veupathdb_auth_token,
        capture_dir=capture_dir,
    )


@procrastinate_app.task(queue="verification", name="durable:geneset_enrichment")
async def geneset_enrichment_job(
    task_id: str,
    thread_id: str,
    args: dict[str, Any],
    veupathdb_auth_token: str | None = None,
    capture_dir: str | None = None,
) -> None:
    await run_durable_task(
        tool_name="geneset_enrichment",
        task_id=task_id,
        thread_id=thread_id,
        args=args,
        veupathdb_auth_token=veupathdb_auth_token,
        capture_dir=capture_dir,
    )


@procrastinate_app.task(queue="verification", name="durable:run_eda_compute")
async def run_eda_compute_job(
    task_id: str,
    thread_id: str,
    args: dict[str, Any],
    veupathdb_auth_token: str | None = None,
    capture_dir: str | None = None,
) -> None:
    await run_durable_task(
        tool_name="run_eda_compute",
        task_id=task_id,
        thread_id=thread_id,
        args=args,
        veupathdb_auth_token=veupathdb_auth_token,
        capture_dir=capture_dir,
    )


@procrastinate_app.task(queue="chat_turn", name="chat_turn:run")
async def run_chat_turn_job(payload: dict[str, Any]) -> None:
    await run_chat_turn(payload)


@procrastinate_app.periodic(cron="* * * * *")
@procrastinate_app.task(queue="maintenance", name="maintenance:release_stalled_jobs")
async def release_stalled_jobs_job(timestamp: int) -> None:
    del timestamp
    await release_stalled_jobs()


@procrastinate_app.periodic(cron="41 4 * * *")
@procrastinate_app.task(queue="maintenance", name="maintenance:prune_orphan_vectors")
async def prune_orphan_vectors_job(timestamp: int) -> None:
    del timestamp
    await prune_orphan_vectors(ORPHAN_VECTOR_GRACE)


@procrastinate_app.periodic(cron="17 3 * * *")
@procrastinate_app.task(queue="maintenance", name="maintenance:extract_eval_candidates")
async def extract_eval_candidates_job(timestamp: int) -> None:
    del timestamp
    await extract_eval_candidates()
