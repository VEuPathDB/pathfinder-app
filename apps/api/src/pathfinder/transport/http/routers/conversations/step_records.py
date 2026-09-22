"""GET /conversations/{id}/strategy/steps/{step_id}/records - the genes one step answers."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from pathfinder.services.conversations.responses import StepRecordsResponse
from pathfinder.services.conversations.step_records import (
    StepPage,
    read_step_records,
)
from pathfinder.transport.http.deps import AvailableSite, CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@dataclass
class StepPageQuery:
    """The page of genes the request asks for."""

    offset: int = Query(0, ge=0)
    limit: int = Query(50, ge=1, le=500)


@router.get(
    "/{conversation_id:uuid}/strategy/steps/{step_id}/records",
    response_model=StepRecordsResponse,
)
async def get_step_records(
    conversation_id: UUID,
    step_id: str,
    site_id: AvailableSite,
    session: DBSession,
    user_id: CurrentUser,
    query: Annotated[StepPageQuery, Depends()],
) -> StepRecordsResponse:
    """One page of the genes a pushed step answers on its site."""
    return await read_step_records(
        session,
        conversation_id,
        user_id,
        site_id=site_id,
        page=StepPage(step_id=step_id, offset=query.offset, limit=query.limit),
    )
