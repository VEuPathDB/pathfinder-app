"""Worker-side body of one audit job."""

from __future__ import annotations

from pydantic import JsonValue
from veupathdb.wdk import search_turn

from strategist.jobs.auth_context import attach_application
from strategist.services.audit.job import AuditJob, carry_run


async def run_audit_job(payload: dict[str, JsonValue]) -> None:
    job = AuditJob.model_validate(payload)
    async with attach_application():
        with search_turn():
            await carry_run(job)
