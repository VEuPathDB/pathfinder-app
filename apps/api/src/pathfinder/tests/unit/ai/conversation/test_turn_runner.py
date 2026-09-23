"""``_drive_graph`` closes a turn the same way whether it is stopped or dies.

The live stream shows a failure from the ``error`` chunk, which no reducer turns
into a part. ``data-turn-failed`` is the durable footprint beside it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from pathfinder.ai.conversation import turn_failure, turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.tests._support.chunk_log import reduce_chunks_to_messages

_ERROR_TEXT = (
    "The worker running this turn stopped before it finished. "
    "Send the message again to retry."
)


@dataclass
class _StubWriter:
    conversation_id: UUID
    turn_id: UUID
    chunks: list[dict[str, Any]] = field(default_factory=list)

    async def write(self, chunk: dict[str, Any]) -> int:
        self.chunks.append(chunk)
        return len(self.chunks)


@dataclass
class _RuntimeCtx:
    cancel_event: asyncio.Event


class _SlowGraph:
    """Yields one custom chunk after a long sleep, long enough to cancel mid-flight."""

    def __init__(self, sleep_for: float = 5.0) -> None:
        self.sleep_for = sleep_for
        self.was_cancelled = False

    def astream(
        self,
        graph_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
        stream_mode: list[str],
    ) -> AsyncIterator[tuple[str, Any]]:
        del graph_input, config, context, stream_mode
        return self._iter()

    async def _iter(self) -> AsyncIterator[tuple[str, Any]]:
        try:
            await asyncio.sleep(self.sleep_for)
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise
        yield ("custom", {"type": "data-noop"})


class _ToolThenSleepGraph:
    """Emits one open tool call, then sleeps long enough to be stopped."""

    def __init__(self) -> None:
        self.was_cancelled = False

    def astream(
        self,
        graph_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
        stream_mode: str,
    ) -> AsyncIterator[dict[str, Any]]:
        del graph_input, config, context, stream_mode
        return self._iter()

    async def _iter(self) -> AsyncIterator[dict[str, Any]]:
        yield {
            "chunk": {
                "type": "tool-input-available",
                "toolCallId": "call_open",
                "toolName": "think",
                "input": {},
            },
        }
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise


class _RaisingGraph:
    """Fails the way a driver fails: partway through the stream."""

    def astream(
        self,
        graph_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
        stream_mode: str,
    ) -> AsyncIterator[Any]:
        del graph_input, config, context, stream_mode
        return self._iter()

    async def _iter(self) -> AsyncIterator[Any]:
        yield {"chunk": {"type": "text-delta", "id": "t", "delta": "Look"}}
        raise RuntimeError(_ERROR_TEXT)


class _RaisingGraphMidToolCall:
    """Fails while a tool call is open, the way a killed tool call leaves it."""

    def astream(
        self,
        graph_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
        stream_mode: str,
    ) -> AsyncIterator[Any]:
        del graph_input, config, context, stream_mode
        return self._iter()

    async def _iter(self) -> AsyncIterator[Any]:
        yield {
            "chunk": {
                "type": "tool-input-start",
                "toolCallId": "call-1",
                "toolName": "search_eda_studies",
            },
        }
        yield {
            "chunk": {
                "type": "tool-input-available",
                "toolCallId": "call-1",
                "toolName": "search_eda_studies",
                "input": {"limit": 5},
            },
        }
        yield {
            "chunk": {
                "type": "tool-input-start",
                "toolCallId": "call-2",
                "toolName": "list_sites",
            },
        }
        yield {"chunk": {"type": "tool-output-available", "toolCallId": "call-2"}}
        raise RuntimeError(_ERROR_TEXT)


def _body(conversation_id: UUID) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "id": str(conversation_id),
            "trigger": "submit-message",
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "hi"}],
                },
            ],
            "conversationId": str(conversation_id),
            "siteId": "plasmodb",
        },
    )


@pytest.fixture(autouse=True)
def _no_cancel_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_poll(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(turn_runner, "watch_for_cancel", _no_poll)


async def _drive(
    graph: Any,
    writer: _StubWriter,
    *,
    cancel_event: asyncio.Event | None = None,
) -> turn_runner._DriveResult:
    return await turn_runner._drive_graph(
        body=_body(writer.conversation_id),
        graph_input={"turn_message_id": writer.turn_id, "user_id": uuid4()},
        compiled_graph=graph,
        runtime_context=_RuntimeCtx(cancel_event=cancel_event or asyncio.Event()),
        writer=writer,
    )


def _writer() -> _StubWriter:
    return _StubWriter(conversation_id=uuid4(), turn_id=uuid4())


async def _cancel_after(cancel_event: asyncio.Event, delay: float) -> None:
    await asyncio.sleep(delay)
    cancel_event.set()


@pytest.mark.asyncio
async def test_drive_graph_cancels_mid_call_when_event_set() -> None:
    cancel_event = asyncio.Event()
    graph = _SlowGraph(sleep_for=10.0)
    trigger = asyncio.create_task(_cancel_after(cancel_event, 0.05))
    drive = asyncio.create_task(_drive(graph, _writer(), cancel_event=cancel_event))

    result = await asyncio.wait_for(drive, timeout=2.0)
    await trigger

    assert result.cancelled is True
    assert graph.was_cancelled is True


@pytest.mark.asyncio
async def test_a_stop_closes_the_open_tool_call() -> None:
    cancel_event = asyncio.Event()
    writer = _writer()
    trigger = asyncio.create_task(_cancel_after(cancel_event, 0.1))

    result = await asyncio.wait_for(
        _drive(_ToolThenSleepGraph(), writer, cancel_event=cancel_event),
        timeout=2.0,
    )
    await trigger

    assert result.cancelled is True
    closes = [
        c
        for c in writer.chunks
        if c.get("type") == "tool-output-error" and c.get("toolCallId") == "call_open"
    ]
    assert len(closes) == 1
    assert closes[0]["errorText"] == "Stopped by the user."


@pytest.mark.asyncio
async def test_a_raising_graph_writes_the_failure_part_beside_the_error() -> None:
    writer = _writer()

    result = await _drive(_RaisingGraph(), writer)

    assert result.encountered_error is True
    assert [chunk["type"] for chunk in writer.chunks] == [
        "text-delta",
        "error",
        "data-turn-failed",
    ]
    assert writer.chunks[2]["data"] == {"errorText": writer.chunks[1]["errorText"]}


@pytest.mark.asyncio
async def test_a_raising_graph_ends_the_tool_calls_it_left_open() -> None:
    writer = _writer()

    await _drive(_RaisingGraphMidToolCall(), writer)

    assert [chunk["type"] for chunk in writer.chunks] == [
        "tool-input-start",
        "tool-input-available",
        "tool-input-start",
        "tool-output-available",
        "tool-output-error",
        "error",
        "data-turn-failed",
    ]
    assert writer.chunks[4]["toolCallId"] == "call-1"
    assert writer.chunks[4]["errorText"] == writer.chunks[5]["errorText"]


def test_the_log_of_a_failed_turn_reduces_to_a_visible_failure() -> None:
    """The chunk log a failed turn leaves rebuilds into three parts."""
    messages = reduce_chunks_to_messages(
        [
            {
                "type": "user-message",
                "message": {"id": "u1", "role": "user", "parts": []},
            },
            {"type": "data-turn-status", "data": {"label": "Queued"}},
            {"type": "start", "messageId": "a1"},
            {"type": "text-start", "id": "t"},
            {
                "type": "text-delta",
                "id": "t",
                "delta": "Looking at PlasmoDB kinases",
            },
            {"type": "text-end", "id": "t"},
            {"type": "error", "errorText": _ERROR_TEXT},
            {"type": "data-turn-failed", "data": {"errorText": _ERROR_TEXT}},
            {"type": "finish", "finishReason": "error"},
            {"type": "done"},
        ],
    )

    parts = messages[1]["parts"]
    assert [part["type"] for part in parts] == [
        "data-turn-status",
        "text",
        "data-turn-failed",
    ]
    assert parts[2]["data"] == {"errorText": _ERROR_TEXT}


async def test_a_pending_title_is_awaited_and_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A title still running when the turn ends is waited for, not cancelled."""

    async def _slow_title() -> str:
        await asyncio.sleep(0.2)
        return "Kinases in gametocytes"

    async def _named(conversation_id: UUID, *, title: str) -> bool:
        del conversation_id, title
        return True

    monkeypatch.setattr(turn_runner, "name_conversation_if_unnamed", _named)
    title_task = asyncio.create_task(_slow_title())
    writer = _writer()

    await turn_runner._write_title(title_task, writer.conversation_id, writer)

    assert title_task.cancelled() is False
    assert [chunk["type"] for chunk in writer.chunks] == ["data-conversation-title"]
    assert writer.chunks[0]["data"]["title"] == "Kinases in gametocytes"


async def _conversation_that_cannot_load(conversation_id: UUID) -> None:
    del conversation_id
    msg = "the conversations table did not answer"
    raise RuntimeError(msg)


@pytest.mark.asyncio
async def test_a_turn_that_fails_before_its_graph_ends_visibly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The setup steps before the graph close the turn the way a graph failure does."""
    monkeypatch.setattr(
        turn_runner, "load_conversation", _conversation_that_cannot_load
    )
    writer = _StubWriter(conversation_id=uuid4(), turn_id=uuid4())
    body = ChatRequestBody.model_validate(
        {
            "conversationId": str(writer.conversation_id),
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "hi"}],
                },
            ],
            "siteId": "plasmodb",
        },
    )

    with pytest.raises(RuntimeError):
        await turn_runner.run_turn(
            request=turn_runner.TurnRequest(body=body, user_id=uuid4()),
            spec=_spec_never_reached(),
            compiled_graph=None,
            memory_store=None,
            writer=writer,
        )

    kinds = [chunk["type"] for chunk in writer.chunks]
    assert kinds == ["error", "data-turn-failed", "finish", "done"]
    assert writer.chunks[0]["errorText"] == turn_failure.STOPPED_BEFORE_IT_RAN
    assert "the conversations table did not answer" not in writer.chunks[0]["errorText"]
    assert writer.chunks[2]["finishReason"] == "error"


def _spec_never_reached() -> Any:
    class _Spec:
        tool_sources: tuple[Any, ...] = ()

    return _Spec()


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("the gene set store is closed"), TimeoutError()],
)
async def test_a_title_the_store_did_not_take_is_logged_and_the_turn_goes_on(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    """Naming the thread never ends a turn before its finish chunk."""

    async def _title() -> str:
        return "Kinases in gametocytes"

    async def _fails(conversation_id: UUID, *, title: str) -> bool:
        del conversation_id, title
        raise failure

    monkeypatch.setattr(turn_runner, "name_conversation_if_unnamed", _fails)
    writer = _writer()

    await turn_runner._write_title(
        asyncio.create_task(_title()), writer.conversation_id, writer
    )

    assert writer.chunks == []
