"""Message rating routes: rate, clear, and list the rated messages of a thread."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter, Request, Response, status
from pydantic import ConfigDict, Field

from pathfinder.domain.message_rating import Rating
from pathfinder.platform.security import limiter
from pathfinder.services.conversations import message_ratings
from pathfinder.services.conversations.message_ratings import (
    RatedMessage,
    RatedMessageList,
)
from pathfinder.transport.http.deps import CurrentUser, DBSession, MemoryStoreDep

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


class MessageRatingRequest(CamelModel):
    """A like or a dislike of one assistant message."""

    model_config = ConfigDict(extra="forbid")

    rating: Rating = Field(description="The researcher's word on the message.")


@router.put(
    "/{conversation_id}/messages/{message_id}/rating",
    response_model=RatedMessage,
    summary="Like or dislike one assistant message; the latest rating wins.",
)
@limiter.limit("60/minute")
async def rate_message(
    request: Request,
    conversation_id: UUID,
    message_id: UUID,
    body: MessageRatingRequest,
    store: MemoryStoreDep,
    user_id: CurrentUser,
) -> RatedMessage:
    del request
    return await message_ratings.rate_message(
        store=store,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        rating=body.rating,
    )


@router.delete(
    "/{conversation_id}/messages/{message_id}/rating",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Take back the rating of one assistant message.",
)
@limiter.limit("60/minute")
async def clear_message_rating(
    request: Request,
    conversation_id: UUID,
    message_id: UUID,
    store: MemoryStoreDep,
    user_id: CurrentUser,
) -> Response:
    del request
    await message_ratings.clear_message_rating(
        store=store,
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{conversation_id}/ratings",
    response_model=RatedMessageList,
    summary="The rated messages of the conversation.",
)
async def list_message_ratings(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> RatedMessageList:
    return await message_ratings.list_message_ratings(
        session, user_id=user_id, conversation_id=conversation_id
    )
