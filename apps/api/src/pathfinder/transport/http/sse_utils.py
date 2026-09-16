"""Shared helper for simple typed-event SSE streams (not conversation).

Used by experiment/sweep/seed progress streams. Conversation uses the
LangGraph stream-event pipeline; don't use this for chat.

The helper wraps any ``AsyncIterator[BaseModel]`` as a Starlette
``StreamingResponse`` emitting ``text/event-stream`` frames. Each yielded
model becomes one ``event: <name>\\ndata: <json>\\n\\n`` frame. A trailing
``data: [DONE]\\n\\n`` sentinel is always flushed in a ``finally`` block so
browsers (and the frontend ``streamTypedEvents`` consumer) can close cleanly
even when the producer raises mid-stream.

Event names may be homogeneous (``event_name="sweep_point"``) or derived
per event (``event_name=lambda e: e.type``) for heterogeneous streams.
"""

from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# OpenAPI ``responses=`` entry declaring a text/event-stream 200 so the spec
# matches what SSE endpoints actually return.
SSE_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Server-sent event stream.",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
}


def typed_event_stream_response[T: BaseModel](
    events: AsyncIterator[T],
    *,
    event_name: str | Callable[[T], str],
) -> StreamingResponse:
    """Wrap a typed async iterator as a ``text/event-stream`` response.

    :param events: Async iterator yielding Pydantic models. Each model is
        serialized via ``model_dump_json(by_alias=True)`` and emitted as one
        SSE frame.
    :param event_name: Either a constant string (used as the ``event:`` field
        for every frame) or a callable that derives the event name from each
        model - useful for heterogeneous streams where different yields carry
        different event types (e.g. ``sweep_point`` vs ``sweep_complete``).

    :returns: ``StreamingResponse`` with ``media_type="text/event-stream"``.

    The response body terminates with ``data: [DONE]\\n\\n`` even when the
    producer raises - the ``finally`` block flushes the sentinel before the
    exception propagates.
    """
    resolve_name: Callable[[T], str] = (
        (lambda _event: event_name) if isinstance(event_name, str) else event_name
    )

    async def gen() -> AsyncIterator[str]:
        try:
            async for event in events:
                yield f"event: {resolve_name(event)}\n"
                yield f"data: {event.model_dump_json(by_alias=True)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
