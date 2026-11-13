"""One audit run's findings, filtered and paged or as CSV, and one finding with its evidence."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Path, Query
from fastapi.responses import StreamingResponse

from strategist.services.audit.export import finding_lines
from strategist.services.audit.finding_views import (
    MAX_ROW_ID,
    FindingDetail,
    FindingPage,
    FindingQuery,
    finding_detail,
    finding_page,
)
from strategist.services.audit.runs import readable_run
from strategist.transport.http.deps import CurrentUser

router = APIRouter()

_CSV_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The findings as CSV.",
        "content": {"text/csv": {"schema": {"type": "string"}}},
    }
}


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
    "/{run_id}/findings.csv",
    response_class=StreamingResponse,
    responses=_CSV_RESPONSES,
    summary="One audit run's findings as CSV, one row per finding.",
)
async def download_audit_findings(
    run_id: UUID, user_id: CurrentUser
) -> StreamingResponse:
    run = await readable_run(run_id, user_id)
    return StreamingResponse(
        finding_lines(run),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="audit-{run_id}-findings.csv"'
        },
    )


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
