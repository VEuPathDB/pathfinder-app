"""Tests for the shared typed-event SSE helper."""

from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from pathfinder.transport.http.sse_utils import typed_event_stream_response


class Point(BaseModel):
    x: float
    y: float


class StartEvent(BaseModel):
    type: str = "start"
    total: int


class CompleteEvent(BaseModel):
    type: str = "complete"
    count: int


async def _happy_producer() -> AsyncIterator[Point]:
    yield Point(x=1.0, y=2.0)
    yield Point(x=3.5, y=4.5)


async def _empty_producer() -> AsyncIterator[Point]:
    if False:
        yield Point(x=0.0, y=0.0)  # unreachable — makes this a generator


async def _raising_producer() -> AsyncIterator[Point]:
    yield Point(x=1.0, y=2.0)
    msg = "producer crashed"
    raise RuntimeError(msg)


async def _heterogeneous_producer() -> AsyncIterator[StartEvent | CompleteEvent]:
    yield StartEvent(total=2)
    yield CompleteEvent(count=2)


async def _collect_body(resp: StreamingResponse) -> str:
    return "".join(
        [
            chunk if isinstance(chunk, str) else bytes(chunk).decode()
            async for chunk in resp.body_iterator
        ]
    )


async def test_typed_event_stream_response_emits_json_lines() -> None:
    resp = typed_event_stream_response(_happy_producer(), event_name="sweep_point")
    assert isinstance(resp, StreamingResponse)
    assert resp.media_type == "text/event-stream"

    text = await _collect_body(resp)

    # Expect SSE frames with event name and JSON-encoded data.
    assert "event: sweep_point\n" in text
    assert '"x":1.0' in text
    assert '"y":2.0' in text
    assert '"x":3.5' in text
    assert '"y":4.5' in text
    # Final [DONE] sentinel flushed from the `finally` block.
    assert text.endswith("data: [DONE]\n\n")


async def test_typed_event_stream_response_empty_iterator_still_emits_done() -> None:
    resp = typed_event_stream_response(_empty_producer(), event_name="seed")
    text = await _collect_body(resp)
    # No event frames, just the [DONE] sentinel.
    assert text == "data: [DONE]\n\n"


async def test_typed_event_stream_response_exception_mid_stream_flushes_done() -> None:
    """The ``finally`` block must always emit ``[DONE]`` before the exception propagates.

    The producer yields one valid event and then raises. The helper's
    ``finally`` clause runs before the exception bubbles up, so the caller
    sees the valid frame followed by the ``[DONE]`` sentinel — and then
    ``RuntimeError`` reaches them on the next iteration step.
    """
    resp = typed_event_stream_response(_raising_producer(), event_name="sweep_point")
    chunks: list[str] = []
    exc_type: type[BaseException] | None = None
    try:
        async for chunk in resp.body_iterator:
            text = chunk if isinstance(chunk, str) else bytes(chunk).decode()
            chunks.append(text)
    except RuntimeError:
        exc_type = RuntimeError
    text = "".join(chunks)

    assert exc_type is RuntimeError
    assert "event: sweep_point\n" in text
    assert '"x":1.0' in text
    # Even though the producer raised, the generator's `finally` runs,
    # so [DONE] is emitted before the exception propagates to the caller.
    assert "data: [DONE]\n\n" in text


async def test_typed_event_stream_response_heterogeneous_events_via_callable() -> None:
    """Callers may pass a callable to derive event names per event."""
    resp = typed_event_stream_response(
        _heterogeneous_producer(),
        event_name=lambda e: e.type,
    )
    text = await _collect_body(resp)

    assert "event: start\n" in text
    assert "event: complete\n" in text
    assert '"total":2' in text
    assert '"count":2' in text
    assert text.endswith("data: [DONE]\n\n")
