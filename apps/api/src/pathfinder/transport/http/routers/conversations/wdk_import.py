"""WDK-backed strategy open endpoint."""

from fastapi import APIRouter

from pathfinder.services.conversations import wdk_import
from pathfinder.transport.http.deps import CurrentUser, DBSession
from pathfinder.transport.http.schemas import (
    OpenConversationRequest,
    OpenConversationResponse,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post("/open", response_model=OpenConversationResponse)
async def open_strategy(
    request: OpenConversationRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> OpenConversationResponse:
    """Open a strategy by local id or WDK strategy id."""
    conversation_id = await wdk_import.open_strategy(
        session,
        conversation_id=request.conversation_id,
        wdk_strategy_id=request.wdk_strategy_id,
        site_id=request.site_id,
        user_id=user_id,
    )
    # Commit before the response: the caller reads this id back immediately,
    # and the session dependency commits only after the response is sent.
    await session.commit()
    return OpenConversationResponse(conversation_id=conversation_id)
