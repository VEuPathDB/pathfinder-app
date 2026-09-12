from __future__ import annotations

from uuid import UUID

from assistant_core.conversation.authz import assert_owner
from assistant_core.conversation.event_stream import (
    EventsSnapshot,
    fetch_snapshot_chunks,
    iter_sse,
)
from assistant_core.conversation.vercel_adapter import VERCEL_AI_DSP_HEADERS
from fastapi import APIRouter, Query, status
from fastapi.responses import Response, StreamingResponse

from pathfinder.services.conversations.turn_liveness import turn_is_in_flight
from pathfinder.transport.http.deps import CurrentUser, DBSession

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get(
    "/{conversation_id}/events",
    summary=(
        "SSE: tail live turn chunks plus any post-resume continuation "
        "from a suspended durable task. 204 only when nothing is in flight."
    ),
)
async def conversation_events(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
    after: int = Query(default=0, ge=0),
) -> Response:
    await assert_owner(session, conversation_id, user_id)
    if not await turn_is_in_flight(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
    ):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return StreamingResponse(
        iter_sse(conversation_id=conversation_id, after=after),
        media_type="text/event-stream",
        headers=dict(VERCEL_AI_DSP_HEADERS),
    )


@router.get(
    "/{conversation_id}/events/snapshot",
    response_model=EventsSnapshot,
)
async def conversation_events_snapshot(
    conversation_id: UUID,
    session: DBSession,
    user_id: CurrentUser,
) -> EventsSnapshot:
    await assert_owner(session, conversation_id, user_id)
    return await fetch_snapshot_chunks(conversation_id)
