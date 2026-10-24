"""One audit run's findings, filtered and paged, and one finding with its evidence."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query

from pathfinder.services.audit.finding_views import (
    MAX_ROW_ID,
    FindingDetail,
    FindingPage,
    FindingQuery,
    finding_detail,
    finding_page,
)
from pathfinder.transport.http.deps import CurrentUser

router = APIRouter()


@router.get(
    "/{run_id}/findings",
    response_model=FindingPage,
    summary="One audit run's findings, filtered and paged.",
)
async def list_audit_findings(
    run_id: UUID,
    user_id: CurrentUser,
    query: Annotated[FindingQuery, Query()],
) -> FindingPage:
    return await finding_page(run_id, user_id, query)


@router.get(
    "/{run_id}/findings/{finding_id}",
    response_model=FindingDetail,
    summary="One audit finding and the evidence stored for it.",
)
async def get_audit_finding(
    run_id: UUID,
    finding_id: Annotated[int, Path(ge=1, le=MAX_ROW_ID)],
    user_id: CurrentUser,
) -> FindingDetail:
    return await finding_detail(run_id, finding_id, user_id)
