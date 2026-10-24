"""The current user's audit runs, one run's scope, stages, genomes and counts, and a start of a stored run."""

from uuid import UUID

from fastapi import APIRouter, Depends

from pathfinder.services.audit.page_start import start_from_page
from pathfinder.services.audit.views import (
    AuditRunSummary,
    AuditRunView,
    list_runs,
    run_view,
)
from pathfinder.transport.http.deps import (
    CurrentUser,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas.audits import AuditStart

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


@router.post(
    "/{run_id}/start",
    response_model=AuditRunView,
    summary="Resume a stopped audit run, or retry what a finished one left unread.",
    dependencies=[Depends(require_registered_wdk_identity)],
)
async def start_audit_run(
    run_id: UUID, body: AuditStart, user_id: CurrentUser
) -> AuditRunView:
    return await start_from_page(run_id, user_id, body.action)
