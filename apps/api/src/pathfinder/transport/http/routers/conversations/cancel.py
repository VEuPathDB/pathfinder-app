from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import Response

from pathfinder.services.conversations.cancellation import cancel_active_turn
from pathfinder.transport.http.deps import CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post(
    "/{conversation_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def cancel_conversation(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> Response:
    await cancel_active_turn(session, conversation_id=conversation_id, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
