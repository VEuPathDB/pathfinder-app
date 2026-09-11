"""One sub-agent's inner events, rendered onto the chat stream.

A tool call, its result and any text the sub-agent wrote become
``data-sub-agent-step`` chunks; a call awaiting an answer becomes a tool part.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.stream_events import (
    SubAgentStepPayload,
    sub_agent_step_event,
)
from assistant_core.graph.turn_state import SubAgentApprovalCall
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartEndEvent,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.ui.vercel_ai.response_types import (
    DataChunk,
    FileChunk,
    SourceDocumentChunk,
    SourceUrlChunk,
    ToolApprovalRequestChunk,
    ToolInputAvailableChunk,
    ToolInputStartChunk,
    ToolOutputAvailableChunk,
    ToolOutputDeniedChunk,
)

from pathfinder.ai.capabilities.error_classification import is_error_directive

_RESULT_LIMIT = 8000

_STREAMABLE_METADATA = (DataChunk, SourceUrlChunk, SourceDocumentChunk, FileChunk)

type StreamableChunk = DataChunk | SourceUrlChunk | SourceDocumentChunk | FileChunk


def _emit_step(writer: Any, payload: SubAgentStepPayload) -> None:
    emit_chunk(writer, sub_agent_step_event(payload))


def _short(s: str, *, limit: int = 280) -> str:
    return s if len(s) <= limit else s[:limit] + "..."


def _summarize_tool_result(content: object) -> str:
    if isinstance(content, BaseModel):
        return _short(json.dumps(content.model_dump(mode="json")), limit=_RESULT_LIMIT)
    if isinstance(content, str):
        return _short(content, limit=_RESULT_LIMIT)
    try:
        return _short(json.dumps(content), limit=_RESULT_LIMIT)
    except TypeError, ValueError:
        return _short(str(content), limit=_RESULT_LIMIT)


def _result_summary(result: ToolReturnPart | RetryPromptPart) -> str:
    """One-line rendering of an inner tool's result."""
    if isinstance(result, RetryPromptPart):
        content = result.content
        return _short(
            content if isinstance(content, str) else result.model_response(),
            limit=_RESULT_LIMIT,
        )
    return _summarize_tool_result(result.content)


def _step_state(
    result: ToolReturnPart | RetryPromptPart,
) -> Literal["completed", "failed", "denied"]:
    """Terminal state of one inner tool call. A denial is the user's decision,
    not a failure."""
    if isinstance(result, RetryPromptPart):
        return "failed"
    if result.outcome == "denied":
        return "denied"
    return "failed" if is_error_directive(result.content) else "completed"


class _InnerToolSummary(CamelModel):
    """The line an inner tool wrote about its own call."""

    model_config = ConfigDict(extra="ignore")

    summary: str = ""


@dataclass(frozen=True)
class _InnerMetadata:
    """An inner tool's metadata, split into its line and what the stream shows."""

    summary: str | None
    forwarded: list[StreamableChunk]


def _read_tool_metadata(metadata: object) -> _InnerMetadata:
    """Take the inner tool's own line out of its metadata.

    A summary names the inner call, which no reducer on the main stream holds,
    so it becomes the step row's text instead of a chunk. Every other chunk is
    forwarded: a sub-agent tool runs outside the VercelAIAdapter, so the
    adapter does not emit them.
    """
    if not isinstance(metadata, list):
        return _InnerMetadata(summary=None, forwarded=[])
    summary: str | None = None
    forwarded: list[StreamableChunk] = []
    for chunk in metadata:
        if isinstance(chunk, DataChunk) and chunk.type == "data-tool-summary":
            summary = _InnerToolSummary.model_validate(chunk.data).summary or None
        elif isinstance(chunk, _STREAMABLE_METADATA):
            forwarded.append(chunk)
    return _InnerMetadata(summary=summary, forwarded=forwarded)


def _forward_inner_event(
    *,
    parent_tool_call_id: str,
    writer: Any,
    inner_calls: dict[str, str],
    event: AgentStreamEvent,
) -> None:
    """Translate one inner-agent stream event into a
    ``data-sub-agent-step`` chunk for the frontend."""
    if isinstance(event, FunctionToolCallEvent):
        inner_calls[event.tool_call_id] = event.part.tool_name
        _emit_step(
            writer,
            SubAgentStepPayload(
                parent_tool_call_id=parent_tool_call_id,
                kind="tool",
                state="started",
                tool_call_id=event.tool_call_id,
                tool_name=event.part.tool_name,
                args=event.part.args_as_dict(),
            ),
        )
        return
    if isinstance(event, FunctionToolResultEvent):
        tool_name = inner_calls.get(event.tool_call_id)
        if tool_name is None:
            return
        result = event.part
        inner = (
            _read_tool_metadata(result.metadata)
            if isinstance(result, ToolReturnPart)
            else _InnerMetadata(summary=None, forwarded=[])
        )
        _emit_step(
            writer,
            SubAgentStepPayload(
                parent_tool_call_id=parent_tool_call_id,
                kind="tool",
                state=_step_state(result),
                tool_call_id=event.tool_call_id,
                tool_name=tool_name,
                result_summary=inner.summary or _result_summary(result),
            ),
        )
        for chunk in inner.forwarded:
            emit_chunk(writer, chunk)
        return
    if isinstance(event, PartEndEvent):
        part = event.part
        if not isinstance(part, (TextPart, ThinkingPart)) or not part.content.strip():
            return
        _emit_step(
            writer,
            SubAgentStepPayload(
                parent_tool_call_id=parent_tool_call_id,
                kind="text" if isinstance(part, TextPart) else "reasoning",
                state="completed",
                text=_short(part.content, limit=2000),
            ),
        )


def _announce_approval(writer: Any, call: ToolCallPart) -> SubAgentApprovalCall:
    """Render one inner tool call as a tool part awaiting the user's answer."""
    args = call.args_as_dict()
    emit_chunk(
        writer,
        ToolInputStartChunk(tool_call_id=call.tool_call_id, tool_name=call.tool_name),
    )
    emit_chunk(
        writer,
        ToolInputAvailableChunk(
            tool_call_id=call.tool_call_id,
            tool_name=call.tool_name,
            input=args,
        ),
    )
    emit_chunk(
        writer,
        ToolApprovalRequestChunk(
            approval_id=call.tool_call_id,
            tool_call_id=call.tool_call_id,
        ),
    )
    return SubAgentApprovalCall(
        tool_call_id=call.tool_call_id,
        tool_name=call.tool_name,
        args=args,
    )


def _close_answered_approval(
    writer: Any,
    event: FunctionToolResultEvent,
    answered: frozenset[str],
) -> None:
    """Put an answered tool part into its terminal state on the client."""
    if event.tool_call_id not in answered:
        return
    result = event.part
    if isinstance(result, ToolReturnPart) and result.outcome == "denied":
        emit_chunk(writer, ToolOutputDeniedChunk(tool_call_id=event.tool_call_id))
        return
    emit_chunk(
        writer,
        ToolOutputAvailableChunk(
            tool_call_id=event.tool_call_id,
            output=_result_summary(result),
        ),
    )
