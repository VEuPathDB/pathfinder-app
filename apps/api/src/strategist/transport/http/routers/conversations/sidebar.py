from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from strategist.services.conversations.service import ConversationService
from strategist.transport.http.deps import CurrentUser, DBSession
from strategist.transport.http.schemas import ConversationDuplicateResponse

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post(
    "/{conversation_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a conversation (hide from sidebar).",
)
async def dismiss_conversation(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> None:
    await ConversationService(session).dismiss(conversation_id, user_id)


@router.post(
    "/{conversation_id}/duplicate",
    response_model=ConversationDuplicateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Clone a conversation (new row + copied messages).",
)
async def duplicate_conversation(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> ConversationDuplicateResponse:
    dup = await ConversationService(session).duplicate(conversation_id, user_id)
    return ConversationDuplicateResponse(id=dup.id, name=dup.name)
