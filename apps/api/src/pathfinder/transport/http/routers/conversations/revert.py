from __future__ import annotations

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter, Depends, HTTPException, status

from pathfinder.services.conversations.revert import (
    RevertError,
    revert_conversation_to_message,
)
from pathfinder.services.strategies.abandoned_mint import delete_released_mint
from pathfinder.transport.http.deps import (
    CurrentUser,
    DBSession,
    require_registered_wdk_identity,
)

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


class RevertRequest(CamelModel):
    message_id: UUID


# A revert restores the target's snapshot as a strategy of the user's own,
# so it writes to WDK exactly as a branch does.
@router.post(
    "/{conversation_id}/revert-to-message",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete all state at or after the target user message.",
    dependencies=[Depends(require_registered_wdk_identity)],
)
async def revert_to_message(
    conversation_id: UUID,
    request: RevertRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> None:
    try:
        release = await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=request.message_id,
            user_id=user_id,
        )
    except RevertError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    await delete_released_mint(release)
