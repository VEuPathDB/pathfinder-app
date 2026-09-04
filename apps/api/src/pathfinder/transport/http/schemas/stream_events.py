"""The chat stream's event union. The generated client needs it, so the
OpenAPI post-pass anchors it into the spec."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field
from pydantic.alias_generators import to_camel


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=to_camel,
    )


class ToolCallDelta(_Base):
    tool_call_id: str
    tool_name: str | None = None
    arguments_delta: str = ""


class MessagesPartialEvent(_Base):
    type: Literal["messages/partial"] = "messages/partial"
    message_id: str
    delta: str = ""
    tool_call_deltas: list[ToolCallDelta] = Field(default_factory=list)
    reasoning_delta: str = ""


class CompletedToolCall(_Base):
    id: str
    name: str
    arguments: dict[str, object]


class MessagesCompleteEvent(_Base):
    type: Literal["messages/complete"] = "messages/complete"
    message_id: str
    role: Literal["human", "ai", "tool", "system"]
    content: str = ""
    tool_calls: list[CompletedToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    reasoning: str = ""


class UpdatesEvent(_Base):
    type: Literal["updates"] = "updates"
    node: str
    writes: dict[str, object]


class CustomEvent(_Base):
    type: Literal["custom"] = "custom"
    kind: str
    data: dict[str, object]


class InterruptPayload(_Base):
    id: str
    value: dict[str, object]


class InterruptsEvent(_Base):
    type: Literal["interrupts"] = "interrupts"
    interrupts: list[InterruptPayload]


class CheckpointEvent(_Base):
    type: Literal["checkpoint"] = "checkpoint"
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    node: str | None = None
    step: int
    created_at: str


class ErrorEvent(_Base):
    type: Literal["error"] = "error"
    message: str
    code: str | None = None


class DoneEvent(_Base):
    type: Literal["done"] = "done"
    reason: Literal["completed", "interrupted", "error"]


StreamEvent = Annotated[
    MessagesPartialEvent
    | MessagesCompleteEvent
    | UpdatesEvent
    | CustomEvent
    | InterruptsEvent
    | CheckpointEvent
    | ErrorEvent
    | DoneEvent,
    Discriminator("type"),
]
