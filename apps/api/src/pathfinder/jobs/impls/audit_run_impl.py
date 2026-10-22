"""Worker-side body of one audit job."""

from __future__ import annotations

from pydantic import JsonValue
from veupathdb.wdk import search_definitions_read_once, search_turn

from pathfinder.jobs.auth_context import attach_application
from pathfinder.services.audit.job import AuditJob, carry_run


async def run_audit_job(payload: dict[str, JsonValue]) -> None:
    job = AuditJob.model_validate(payload)
    async with attach_application():
        with search_turn(), search_definitions_read_once():
            await carry_run(job)
