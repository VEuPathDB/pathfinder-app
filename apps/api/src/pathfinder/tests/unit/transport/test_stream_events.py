"""The chat stream event union serializes and parses by discriminator."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from pathfinder.transport.http.schemas.stream_events import (
    CheckpointEvent,
    CompletedToolCall,
    CustomEvent,
    DoneEvent,
    InterruptPayload,
    InterruptsEvent,
    MessagesCompleteEvent,
    MessagesPartialEvent,
    StreamEvent,
    UpdatesEvent,
)

ADAPTER: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)


def test_messages_partial_roundtrip() -> None:
    ev = MessagesPartialEvent(message_id="m1", delta="Hi")
    dumped = ev.model_dump(by_alias=True, mode="json")
    assert dumped["type"] == "messages/partial"
    assert dumped["messageId"] == "m1"
    assert dumped["delta"] == "Hi"
    assert dumped["toolCallDeltas"] == []
    parsed = ADAPTER.validate_python(dumped)
    assert isinstance(parsed, MessagesPartialEvent)
    assert parsed.message_id == "m1"


def test_messages_complete_tool_calls() -> None:
    ev = MessagesCompleteEvent(
        message_id="m2",
        role="ai",
        content="",
        tool_calls=[CompletedToolCall(id="t1", name="do_thing", arguments={"k": 1})],
    )
    dumped = ev.model_dump(by_alias=True, mode="json")
    assert dumped["toolCalls"][0]["name"] == "do_thing"
    parsed = ADAPTER.validate_python(dumped)
    assert isinstance(parsed, MessagesCompleteEvent)
    assert parsed.tool_calls[0].arguments == {"k": 1}


def test_custom_event() -> None:
    ev = CustomEvent(
        kind="data-graph-cleared", data={"reason": "user cleared the strategy"}
    )
    dumped = ev.model_dump(by_alias=True, mode="json")
    assert dumped["kind"] == "data-graph-cleared"
    parsed = ADAPTER.validate_python(dumped)
    assert isinstance(parsed, CustomEvent)
    assert parsed.data == {"reason": "user cleared the strategy"}


def test_checkpoint_event() -> None:
    ev = CheckpointEvent(
        checkpoint_id="cp-1",
        parent_checkpoint_id="cp-0",
        node="supervisor",
        step=3,
        created_at="2026-04-15T10:00:00+00:00",
    )
    dumped = ev.model_dump(by_alias=True, mode="json")
    assert dumped["checkpointId"] == "cp-1"
    assert dumped["parentCheckpointId"] == "cp-0"


def test_interrupts_event() -> None:
    ev = InterruptsEvent(
        interrupts=[
            InterruptPayload(id="i1", value={"kind": "durable_task", "task_id": "t"})
        ]
    )
    dumped = ev.model_dump(by_alias=True, mode="json")
    assert len(dumped["interrupts"]) == 1


def test_done_event() -> None:
    ev = DoneEvent(reason="completed")
    dumped = ev.model_dump(by_alias=True, mode="json")
    assert dumped["type"] == "done"
    assert dumped["reason"] == "completed"


def test_updates_event() -> None:
    ev = UpdatesEvent(node="scoping", writes={"foo": "bar"})
    dumped = ev.model_dump(by_alias=True, mode="json")
    assert dumped["type"] == "updates"
    assert dumped["node"] == "scoping"
    assert dumped["writes"] == {"foo": "bar"}


def test_discriminator_rejects_bad_type() -> None:
    with pytest.raises(ValidationError):
        ADAPTER.validate_python({"type": "bogus", "data": {}})


def test_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        MessagesPartialEvent.model_validate(
            {
                "type": "messages/partial",
                "messageId": "m",
                "delta": "x",
                "unexpected": True,
            }
        )


def test_parse_from_json_line() -> None:
    line = json.dumps({"type": "done", "reason": "completed"})
    assert ADAPTER.validate_json(line) == DoneEvent(type="done", reason="completed")
