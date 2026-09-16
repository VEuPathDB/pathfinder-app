"""POST /conversations/{id}/save-substrategy - clone a subtree to a new WDK saved strategy."""

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter, Depends

from pathfinder.services.conversations.service import ConversationService
from pathfinder.transport.http.deps import (
    AvailableSite,
    CurrentUser,
    DBSession,
    RequiredSiteIdQuery,
    require_registered_wdk_identity,
)
from pathfinder.transport.http.schemas import (
    SaveSubstrategyRequest,
    SaveSubstrategyResponse,
)


class SavedStrategyConsumerCounts(CamelModel):
    """Map of WDK strategy id -> number of conversations that import it."""

    counts: dict[int, int]


router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post(
    "/{conversation_id:uuid}/save-substrategy",
    response_model=SaveSubstrategyResponse,
    dependencies=[Depends(require_registered_wdk_identity)],
)
async def save_substrategy(
    conversation_id: UUID,
    request: SaveSubstrategyRequest,
    site_id: AvailableSite,
    session: DBSession,
    user_id: CurrentUser,
) -> SaveSubstrategyResponse:
    """Save a subtree of the active strategy as a new WDK saved strategy."""
    result = await ConversationService(session).save_substrategy(
        conversation_id,
        user_id,
        site_id=site_id,
        step_id=request.step_id,
        name=request.name,
        description=request.description,
    )
    return SaveSubstrategyResponse(
        wdk_strategy_id=result.wdk_strategy_id,
        name=result.name,
        description=result.description,
        record_type=result.record_type,
        root_step_id=result.root_step_id,
    )


@router.get(
    "/saved-strategy-consumers",
    response_model=SavedStrategyConsumerCounts,
)
async def get_saved_strategy_consumer_counts(
    site_id: RequiredSiteIdQuery,
    session: DBSession,
    user_id: CurrentUser,
) -> SavedStrategyConsumerCounts:
    """Count how many conversations consume each saved strategy."""
    counts = await ConversationService(session).count_saved_strategy_consumers(
        user_id,
        site_id,
    )
    return SavedStrategyConsumerCounts(counts=counts)
