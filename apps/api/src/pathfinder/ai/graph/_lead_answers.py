"""How a user's answer to a parked call is read.

The approve or deny recorded for each call, the message the user typed instead
of clicking, and the calls the same Lead response left unresolved beside the
one they answered.
"""

from __future__ import annotations

from assistant_core.capabilities.input_screening import is_pure_approval
from assistant_core.graph import approvals
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolReturnPart,
)
from pydantic_ai.tools import DeferredToolApprovalResult, ToolDenied

from pathfinder.ai.graph.state import PipelineState

__all__ = [
    "answers_for",
    "sibling_answers",
    "typed_reply",
    "unanswered_inner",
]

_DENIED_BY_REPLY = "The user replied instead of answering the approval."


def answers_for(
    state: PipelineState,
    tool_call_ids: list[str],
) -> dict[str, bool | DeferredToolApprovalResult]:
    """The user's approve/deny for each of ``tool_call_ids``, when answered."""
    answers: dict[str, bool | DeferredToolApprovalResult] = {}
    for tool_call_id in tool_call_ids:
        response = state.approval_responses.get(tool_call_id)
        if response is None:
            continue
        answers[tool_call_id] = approvals.approval_answer(response)
    return answers


def typed_reply(state: PipelineState) -> str | None:
    """The user's new message, when one arrives while an approval is pending.

    Answering the card leaves ``user_message_id`` untouched, so a different id
    is a message the user typed instead of clicking.
    """
    approval = state.pending_approval
    if approval is None or approval.user_message_id is None:
        return None
    if state.user_message_id in (None, approval.user_message_id):
        return None
    return state.user_prompt.strip() or None


def _settled_call_ids(history: list[ModelMessage]) -> set[str]:
    """Tool calls that already carry a result in the replayed history."""
    settled: set[str] = set()
    for message in history:
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if isinstance(part, ToolReturnPart | RetryPromptPart) and part.tool_call_id:
                settled.add(part.tool_call_id)
    return settled


def sibling_answers(
    state: PipelineState,
    approval: PendingApproval,
) -> dict[str, bool | DeferredToolApprovalResult]:
    """Answers for the other calls the same Lead response left unresolved."""
    history = approvals.resume_history(approval)
    last_response = next(
        (m for m in reversed(history) if isinstance(m, ModelResponse)),
        None,
    )
    if last_response is None:
        return {}
    settled = _settled_call_ids(history)
    return answers_for(
        state,
        [
            call.tool_call_id
            for call in last_response.tool_calls
            if call.tool_call_id != approval.tool_call_id
            and call.tool_call_id not in settled
        ],
    )


def unanswered_inner(
    state: PipelineState,
    approval: PendingApproval,
    inner_ids: list[str],
) -> tuple[dict[str, bool | DeferredToolApprovalResult], str | None]:
    """How to resolve inner approvals the user did not click.

    An answer naming the dispatch call applies to all of them. A typed reply
    approves them when it is nothing but an approval phrase, and otherwise
    denies them and is delivered to the Lead as the user's next message.
    """
    dispatch_answer = answers_for(state, [approval.tool_call_id])
    if dispatch_answer:
        answer = dispatch_answer[approval.tool_call_id]
        return dict.fromkeys(inner_ids, answer), None
    typed = typed_reply(state)
    if typed is None:
        return {}, None
    if is_pure_approval(typed):
        approved: bool | DeferredToolApprovalResult = True
        return dict.fromkeys(inner_ids, approved), None
    denial: bool | DeferredToolApprovalResult = ToolDenied(message=_DENIED_BY_REPLY)
    return dict.fromkeys(inner_ids, denial), typed
