"""The current user's audit runs, and one run's scope, stages, genomes and counts."""

from uuid import UUID

from fastapi import APIRouter

from pathfinder.services.audit.views import (
    AuditRunSummary,
    AuditRunView,
    list_runs,
    run_view,
)
from pathfinder.transport.http.deps import CurrentUser

router = APIRouter()


@router.get(
    "",
    response_model=list[AuditRunSummary],
    summary="The current user's audit runs, newest first.",
)
async def list_audit_runs(user_id: CurrentUser) -> list[AuditRunSummary]:
    return await list_runs(user_id)


@router.get(
    "/{run_id}",
    response_model=AuditRunView,
    summary="One audit run: its scope, stages, genomes and finding counts.",
)
async def get_audit_run(run_id: UUID, user_id: CurrentUser) -> AuditRunView:
    return await run_view(run_id, user_id)
