from __future__ import annotations

from uuid import UUID

from assistant_core.conversation.authz import assert_owner
from assistant_core.conversation.event_stream import (
    EventsSnapshot,
    fetch_snapshot_chunks,
    iter_sse,
    latest_event,
)
from assistant_core.conversation.vercel_adapter import VERCEL_AI_DSP_HEADERS
from assistant_core.tasks.service import has_active_task
from fastapi import APIRouter, Query, status
from fastapi.responses import Response, StreamingResponse

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
    tip = await latest_event(conversation_id)
    turn_in_flight = tip is not None and tip[1].get("type") != "done"
    # When the latest chunk is a turn terminator AND no durable task is still
    # running, nothing is in flight → 204. (A running task's resume writes new
    # chunks, so we must tail in that case.)
    if not turn_in_flight and not await has_active_task(
        session,
        conversation_id,
        user_id,
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
