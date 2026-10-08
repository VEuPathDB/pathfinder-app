from __future__ import annotations

from uuid import UUID

from assistant_core.conversation.event_stream import iter_sse
from assistant_core.conversation.vercel_adapter import VERCEL_AI_DSP_HEADERS
from fastapi.responses import StreamingResponse


def event_tail(conversation_id: UUID, *, after: int) -> StreamingResponse:
    return StreamingResponse(
        iter_sse(conversation_id=conversation_id, after=after),
        media_type="text/event-stream",
        headers={**VERCEL_AI_DSP_HEADERS, "Cache-Control": "no-cache, no-transform"},
    )
