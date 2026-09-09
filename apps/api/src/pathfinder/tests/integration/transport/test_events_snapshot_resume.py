from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
from assistant_core.conversation.event_stream import iter_sse
from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.persistence.models import Conversation

from pathfinder.tests._support.chunk_log import reduce_chunks_to_messages

from ._events_snapshot_support import seed_chunks


def _parse_sse_frames(frames: list[str]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for frame in frames:
        for line in frame.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: ") :]
            if payload == "[DONE]":
                chunks.append({"type": "done"})
                continue
            chunks.append(json.loads(payload))
    return chunks


def _assert_tool_chunks_well_formed(chunks: list[dict[str, Any]]) -> None:
    seen_starts: set[str] = set()
    for chunk in chunks:
        ctype = chunk.get("type")
        tcid = chunk.get("toolCallId")
        if ctype == "tool-input-start" and isinstance(tcid, str):
            seen_starts.add(tcid)
            continue
        if ctype in {
            "tool-input-delta",
            "tool-input-available",
            "tool-input-error",
            "tool-output-available",
            "tool-output-error",
        } and isinstance(tcid, str):
            assert tcid in seen_starts, (
                f"{ctype} for {tcid} arrived without a preceding "
                f"tool-input-start in the resume stream"
            )


async def test_resume_stream_after_snapshot_cap_replays_tool_input_start(
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    """Reproduces the prod failure: an in-flight assistant turn with an
    open tool call, plus a rogue user-message persisted mid-turn. The
    snapshot endpoint must cap such that the SSE replay served by
    `/events?after=cursor` still begins before the tool-input-start —
    otherwise the SDK errors with `tool-input-delta for missing tool call`.
    """
    user_a = uuid4()
    asst_a = uuid4()
    user_first = uuid4()
    asst_b = uuid4()
    user_rogue = uuid4()
    in_flight = [
        user_message_chunk(
            message_id=str(user_a),
            parts=[{"type": "text", "text": "warm-up"}],
        ),
        {"type": "start", "messageId": str(asst_a)},
        {"type": "text-start", "id": "t0"},
        {"type": "text-delta", "id": "t0", "delta": "ok"},
        {"type": "text-end", "id": "t0"},
        {"type": "finish"},
        {"type": "done"},
        user_message_chunk(
            message_id=str(user_first),
            parts=[{"type": "text", "text": "now do the thing"}],
        ),
        {"type": "start", "messageId": str(asst_b)},
        {
            "type": "tool-input-start",
            "toolCallId": "call_inflight",
            "toolName": "do_thing",
        },
        {
            "type": "tool-input-delta",
            "toolCallId": "call_inflight",
            "inputTextDelta": '{"q":',
        },
        user_message_chunk(
            message_id=str(user_rogue),
            parts=[{"type": "text", "text": "rogue mid-turn"}],
        ),
        {
            "type": "tool-input-delta",
            "toolCallId": "call_inflight",
            "inputTextDelta": '"x"}',
        },
    ]
    await seed_chunks(conversation_id=conversation.id, chunks=in_flight)

    snap = (
        await api_client.get(
            f"/api/v1/conversations/{conversation.id}/events/snapshot",
        )
    ).json()
    snap_messages = reduce_chunks_to_messages(snap["chunks"])
    assert [m["role"] for m in snap_messages] == ["user", "assistant", "user"]
    assert snap_messages[2]["id"] == str(user_first)

    completion = [
        {
            "type": "tool-input-available",
            "toolCallId": "call_inflight",
            "toolName": "do_thing",
            "input": {"q": "x"},
        },
        {"type": "finish"},
        {"type": "done"},
    ]
    await seed_chunks(conversation_id=conversation.id, chunks=completion)

    frames: list[str] = [
        frame
        async for frame in iter_sse(
            conversation_id=conversation.id,
            after=snap["cursor"],
        )
    ]
    resume_chunks = _parse_sse_frames(frames)

    resume_types = [c["type"] for c in resume_chunks]
    assert resume_types[0] == "start"
    assert "tool-input-start" in resume_types
    assert resume_types[-1] == "done"
    assert "user-message" not in resume_types

    _assert_tool_chunks_well_formed(resume_chunks)


async def test_snapshot_names_the_message_a_suspended_turn_left_open(
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    """A turn parked on a durable task keeps its message open, and the
    snapshot names it plus the cursor a tail replays it from."""
    user_a = uuid4()
    asst_a = uuid4()
    seeded = [
        user_message_chunk(
            message_id=str(user_a),
            parts=[{"type": "text", "text": "run the controls"}],
        ),
        {"type": "start", "messageId": str(asst_a)},
        {
            "type": "tool-input-available",
            "toolCallId": "call_controls",
            "toolName": "run_control_tests_on_step",
            "input": {"stepId": 7},
        },
        {"type": "finish", "finishReason": "other"},
        {"type": "done"},
    ]
    await seed_chunks(conversation_id=conversation.id, chunks=seeded)

    body = (
        await api_client.get(
            f"/api/v1/conversations/{conversation.id}/events/snapshot",
        )
    ).json()

    assert body["openMessage"] == {
        "messageId": str(asst_a),
        "after": body["cursor"] - 4,
    }
    frames = [
        frame
        async for frame in iter_sse(
            conversation_id=conversation.id,
            after=body["openMessage"]["after"],
        )
    ]
    replayed = _parse_sse_frames(frames)
    assert replayed[0] == {"type": "start", "messageId": str(asst_a)}


async def test_snapshot_names_no_open_message_when_the_turn_closed(
    api_client: httpx.AsyncClient,
    conversation: Conversation,
) -> None:
    user_a = uuid4()
    asst_a = uuid4()
    seeded = [
        user_message_chunk(
            message_id=str(user_a),
            parts=[{"type": "text", "text": "what's the count?"}],
        ),
        {"type": "start", "messageId": str(asst_a)},
        {"type": "text-start", "id": "t1"},
        {"type": "text-delta", "id": "t1", "delta": "42"},
        {"type": "text-end", "id": "t1"},
        {"type": "finish", "finishReason": "stop"},
        {"type": "done"},
    ]
    await seed_chunks(conversation_id=conversation.id, chunks=seeded)

    body = (
        await api_client.get(
            f"/api/v1/conversations/{conversation.id}/events/snapshot",
        )
    ).json()

    assert body["openMessage"] is None
    assert [chunk["type"] for chunk in body["chunks"]] == [
        "user-message",
        "start",
        "text-start",
        "text-delta",
        "text-end",
        "finish",
        "done",
    ]
