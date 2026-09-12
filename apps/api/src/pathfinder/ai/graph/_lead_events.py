"""Translation of the Lead agent's inner stream events into sub-agent cards and ledger refreshes."""

from __future__ import annotations

from typing import Any

from assistant_core.conversation.stream_parts.agent_topology import (
    SubAgentCallPayload,
    sub_agent_call_event,
)
from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.tool_summary import count_noun
from pydantic import BaseModel
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    RetryPromptPart,
    ToolReturnPart,
)
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    ToolApprovalRequestChunk,
    ToolInputAvailableChunk,
    ToolInputDeltaChunk,
    ToolInputErrorChunk,
    ToolInputStartChunk,
    ToolOutputAvailableChunk,
    ToolOutputDeniedChunk,
    ToolOutputErrorChunk,
)

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.graph.stream_events import ledger_update_event
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.sub_agent_tools import (
    TOOL_TO_PHASE_ROLE,
    WIRE_PHASE_BY_ROLE,
    LeadDeps,
    SubAgentCallUsage,
    sub_agent_model_id,
)

# One phase vocabulary for the wire. Every dispatch that runs a sub-agent reads
# it through the role map, so a chunk from the dispatch and a chunk from the run
# name the same phase. ``build_strategy`` runs no sub-agent and names its own.
_SUB_AGENT_ROLE_BY_TOOL: dict[str, PhaseRole] = {
    **TOOL_TO_PHASE_ROLE,
    "build_strategy": "execution",
}
_SUB_AGENT_TOOL_TO_PHASE: dict[str, str] = {
    tool: WIRE_PHASE_BY_ROLE[role] for tool, role in _SUB_AGENT_ROLE_BY_TOOL.items()
}
_SUB_AGENT_TOOL_NAMES = frozenset(_SUB_AGENT_TOOL_TO_PHASE.keys())

# Every chunk that names a tool call. Suppression follows the tool call id,
# not the chunk type, so each of these types must be classified here.
_TOOL_CALL_CHUNKS = (
    ToolInputStartChunk,
    ToolInputDeltaChunk,
    ToolInputAvailableChunk,
    ToolInputErrorChunk,
    ToolOutputAvailableChunk,
    ToolOutputErrorChunk,
)

# Approval chunks stay visible. An approval question the user never sees blocks the turn.
_CHUNKS_EXEMPT_FROM_SUPPRESSION = (
    ToolApprovalRequestChunk,
    ToolOutputDeniedChunk,
)

_NAMED_SUB_AGENT_CHUNKS = (
    ToolInputStartChunk,
    ToolInputAvailableChunk,
    ToolInputErrorChunk,
)


def is_suppressed_sub_agent_chunk(
    chunk: BaseChunk,
    sub_agent_tool_calls: dict[str, str],
) -> bool:
    """Hide the native tool chunks of a sub-agent dispatch.

    The first chunk classifies the dispatch by ``tool_name`` and primes
    ``sub_agent_tool_calls``. Every later chunk of that call is suppressed too.
    """
    if isinstance(chunk, _CHUNKS_EXEMPT_FROM_SUPPRESSION):
        return False
    if not isinstance(chunk, _TOOL_CALL_CHUNKS):
        return False
    if (
        isinstance(chunk, _NAMED_SUB_AGENT_CHUNKS)
        and chunk.tool_name in _SUB_AGENT_TOOL_NAMES
    ):
        sub_agent_tool_calls[chunk.tool_call_id] = chunk.tool_name
        return True
    return chunk.tool_call_id in sub_agent_tool_calls


def _truncate_summary(text: str, limit: int = 280) -> str:
    """Cut to ``limit`` chars on a word boundary, appending ASCII ``...``."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 3].rstrip()
    boundary = cut.rfind(" ")
    if boundary > 0:
        cut = cut[:boundary].rstrip()
    return f"{cut}..."


def _summarize_sub_agent_call_args(args: dict[str, Any]) -> str:
    """One-line input summary for the SubAgentCallCard 'started' state."""
    reason = args.get("reason")
    if isinstance(reason, str) and reason:
        return _truncate_summary(reason)
    return ""


def _summarize_sub_agent_result(result: ToolReturnPart) -> str:
    """One-line result summary for the SubAgentCallCard 'completed' state."""
    content = result.content
    if isinstance(content, BaseModel):
        return _summarize_delta(content)
    if isinstance(content, dict):
        return _summarize_delta_dict(content)
    return _truncate_summary(str(content))


def _summarize_delta(delta: BaseModel) -> str:
    """One line about what a sub-agent's typed delta reports."""
    return _summarize_delta_dict(delta.model_dump())


def _summarize_outcome(outcome: dict[str, Any]) -> str:
    built = len(outcome.get("pushed_step_ids") or [])
    failed = len(outcome.get("failed_steps") or [])
    if failed > 0:
        return f"Built {built}, {failed} failed"
    return f"Built {count_noun(built, 'step')}"


def _summarize_delta_dict(data: dict[str, Any]) -> str:
    """Compact, human-readable one-liner from a sub-agent's typed delta."""
    if "disposition" in data:
        disposition = data.get("disposition")
        if disposition == "needs_user":
            return count_noun(len(data.get("open_questions") or []), "open question")
        return _truncate_summary(str(data.get("summary") or "Framed"))
    if "actions_taken" in data:
        return count_noun(len(data.get("actions_taken") or []), "recovery action")
    if "outcome" in data:
        return _summarize_outcome(data.get("outcome") or {})
    if "digest" in data:
        success = (data.get("digest") or {}).get("success", False)
        return "Verified successfully" if success else "Issues found"
    return ""


def sub_agent_result_failed(result: ToolReturnPart | RetryPromptPart) -> bool:
    """Report whether a sub-agent dispatch failed.

    A ``RetryPromptPart`` is a re-run request. pydantic-ai closes an
    interrupted call with a ``ToolReturnPart`` whose outcome is ``failed``.
    """
    if isinstance(result, RetryPromptPart):
        return True
    return result.outcome == "failed"


def handle_sub_agent_event(
    deps: LeadDeps,
    writer: Any,
    event: AgentStreamEvent,
    sub_agent_tool_calls: dict[str, str],
    sub_agent_usage: dict[str, SubAgentCallUsage],
) -> None:
    """Emit a sub-agent call card and refresh the ledger when a sub-agent tool runs.

    ``sub_agent_tool_calls`` maps each classified tool call id to its tool name.
    """
    if isinstance(event, FunctionToolCallEvent):
        tool_name = event.part.tool_name
        if tool_name not in _SUB_AGENT_TOOL_NAMES:
            return
        sub_agent_tool_calls[event.tool_call_id] = tool_name
        emit_chunk(
            writer,
            sub_agent_call_event(
                SubAgentCallPayload(
                    tool_call_id=event.tool_call_id,
                    sub_agent=_SUB_AGENT_ROLE_BY_TOOL[tool_name],
                    phase=_SUB_AGENT_TOOL_TO_PHASE[tool_name],
                    state="started",
                    model_id=sub_agent_model_id(tool_name),
                    summary=_summarize_sub_agent_call_args(event.part.args_as_dict()),
                )
            ),
        )
        return
    if isinstance(event, FunctionToolResultEvent):
        result_tool_name = sub_agent_tool_calls.get(event.tool_call_id)
        if result_tool_name is None:
            return
        result = event.part
        if isinstance(result, RetryPromptPart):
            content = result.content
            summary = (
                _truncate_summary(content)
                if isinstance(content, str)
                else "retry requested"
            )
        else:
            summary = _summarize_sub_agent_result(result)
        failed = sub_agent_result_failed(result)
        spent = sub_agent_usage.get(event.tool_call_id, SubAgentCallUsage())
        emit_chunk(
            writer,
            sub_agent_call_event(
                SubAgentCallPayload(
                    tool_call_id=event.tool_call_id,
                    sub_agent=_SUB_AGENT_ROLE_BY_TOOL[result_tool_name],
                    phase=_SUB_AGENT_TOOL_TO_PHASE[result_tool_name],
                    state="failed" if failed else "completed",
                    model_id=sub_agent_model_id(result_tool_name),
                    summary=summary,
                    succeeded=not failed,
                    tokens=spent.tokens,
                    cost_usd=str(spent.cost),
                )
            ),
        )
        ledger = derive_ledger(deps.state, deps.intent)
        emit_chunk(writer, ledger_update_event(ledger=ledger))
