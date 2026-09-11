from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter

from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.services.conversations.responses import ConversationResponse
from pathfinder.services.conversations.service import ConversationService
from pathfinder.transport.http.deps import AvailableSite, CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


class ApplyOperationRequest(CamelModel):
    op: GraphOperation


@router.post(
    "/{strategyId:uuid}/operations",
    response_model=ConversationResponse,
)
async def apply_operation_endpoint(
    strategyId: UUID,
    request: ApplyOperationRequest,
    site_id: AvailableSite,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationResponse:
    """Apply a single graph operation through the unified commit pipeline."""
    return await ConversationService(session).apply_operation(
        strategyId,
        user_id,
        site_id=site_id,
        op=request.op,
    )
