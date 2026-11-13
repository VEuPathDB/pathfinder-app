"""The names of the audit queue and its jobs, and the lock that keeps one job of a run at a time."""

from __future__ import annotations

from uuid import UUID

from assistant_core.tasks.app import task_app

AUDIT_QUEUE = "audit"
AUDIT_JOB = "audit:run"
AUDIT_REVIEW_JOB = "audit:review"
_WORKING = frozenset({"todo", "doing"})


def audit_lock(run_id: UUID) -> str:
    return f"audit-run:{run_id}"


async def working(run_id: UUID) -> bool:
    found = await task_app().job_manager.list_jobs_async(lock=audit_lock(run_id))
    return any(job.status in _WORKING for job in found)
