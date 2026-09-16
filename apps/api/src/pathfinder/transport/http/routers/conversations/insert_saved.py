"""POST /conversations/{id}/insert-saved - user-driven insert of a saved sub-strategy."""

from typing import Literal
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter
from pydantic import Field
from veupathdb.domain.strategy import CombineOp

from pathfinder.services.conversations.service import ConversationService
from pathfinder.transport.http.deps import AvailableSite, CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


CombineOperatorLiteral = Literal[
    "INTERSECT",
    "UNION",
    "MINUS",
    "RMINUS",
    "LONLY",
    "RONLY",
]


class InsertSavedRequest(CamelModel):
    # Empty when the thread has no steps yet: the saved strategy becomes the
    # root instead of a combine input.
    target_step_id: str = Field(default="", max_length=64)
    saved_wdk_strategy_id: int
    operator: CombineOperatorLiteral = "INTERSECT"


class InsertSavedResponse(CamelModel):
    wdk_strategy_id: int
    inserted_saved_wdk_strategy_id: int
    inserted_saved_name: str
    # The new combine, or the inserted root when there was no step to combine.
    combine_step_id: str


@router.post(
    "/{conversation_id:uuid}/insert-saved",
    response_model=InsertSavedResponse,
)
async def insert_saved(
    conversation_id: UUID,
    request: InsertSavedRequest,
    site_id: AvailableSite,
    session: DBSession,
    user_id: CurrentUser,
) -> InsertSavedResponse:
    """Insert a saved WDK strategy beside a target step, or as the thread's root."""
    result = await ConversationService(session).insert_saved(
        conversation_id,
        user_id,
        site_id=site_id,
        target_step_id=request.target_step_id,
        saved_wdk_strategy_id=request.saved_wdk_strategy_id,
        operator=CombineOp(request.operator),
    )
    return InsertSavedResponse(
        wdk_strategy_id=result.wdk_strategy_id,
        inserted_saved_wdk_strategy_id=result.inserted_saved_wdk_strategy_id,
        inserted_saved_name=result.inserted_saved_name,
        combine_step_id=result.combine_step_id,
    )
