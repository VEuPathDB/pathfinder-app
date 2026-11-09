from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status

from pathfinder.services.conversations.sharing import (
    ShareChange,
    ShareSettings,
    ShareState,
    renew_password,
    set_share,
    share_of,
    stop_sharing,
)
from pathfinder.transport.http.deps import CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get(
    "/{conversation_id}/share",
    response_model=ShareState,
    summary="The conversation's share link, or none.",
)
async def get_share(
    conversation_id: UUID, session: DBSession, user_id: CurrentUser
) -> ShareState:
    return await share_of(session, conversation_id=conversation_id, user_id=user_id)


@router.put(
    "/{conversation_id}/share",
    response_model=ShareChange,
    summary="Make or change the conversation's share link.",
)
async def put_share(
    conversation_id: UUID,
    body: ShareSettings,
    session: DBSession,
    user_id: CurrentUser,
) -> ShareChange:
    return await set_share(
        session, conversation_id=conversation_id, user_id=user_id, settings=body
    )


@router.post(
    "/{conversation_id}/share/password",
    response_model=ShareChange,
    summary="Make a new password for the share link; the old one stops working.",
)
async def post_share_password(
    conversation_id: UUID, session: DBSession, user_id: CurrentUser
) -> ShareChange:
    return await renew_password(
        session, conversation_id=conversation_id, user_id=user_id
    )


@router.delete(
    "/{conversation_id}/share",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Stop sharing the conversation.",
)
async def delete_share(
    conversation_id: UUID, session: DBSession, user_id: CurrentUser
) -> Response:
    await stop_sharing(session, conversation_id=conversation_id, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
