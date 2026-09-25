"""The Lead's proposal card, and the edit a yes runs from it.

The card's changes are the edit's brief, so a yes needs nothing the model
remembers. A no never reaches this tool: the turn ends without the Lead.
"""

from __future__ import annotations

from typing import Literal

from assistant_core.conversation.stream_parts.agent_topology import (
    SubAgentCallPayload,
    sub_agent_call_event,
)
from assistant_core.graph.emit import emit_chunk
from langgraph.config import get_stream_writer
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.ai.lead.dispatch_context import defer_dispatch, dispatch_call_id
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.proposal import CardProposal, Proposal
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait
from pathfinder.ai.lead.sub_agent_tools import (
    WIRE_PHASE_BY_ROLE,
    LeadDeps,
    SubAgentCallUsage,
    sub_agent_model_id,
)

_EDIT_TOOL = "edit_strategy"
_EDIT_ROLE = "frame"


def accepted_brief(state: PipelineState, tool_call_id: str, proposal: Proposal) -> str:
    """The edit's brief: the card's changes and the note sent with the yes."""
    answers = state.user_question_answers.get(tool_call_id, [])
    return proposal.brief(" ".join(answer.note for answer in answers if answer.note))


def nothing_to_edit_message(brief: str) -> str:
    """Why an accepted proposal on a thread with no strategy runs no edit."""
    return (
        "The researcher accepted your proposal, and this conversation holds no "
        "strategy yet, so there is nothing to edit. Frame the accepted changes "
        "with frame_problem and build them with build_strategy.\n\n" + brief
    )


def _edit_card(
    deps: LeadDeps,
    tool_call_id: str,
    state: Literal["started", "completed", "failed"],
    summary: str,
) -> None:
    """Draw the accepted proposal's edit as the dispatch card its steps join."""
    spent = deps.sub_agent_usage_by_call.get(tool_call_id, SubAgentCallUsage())
    emit_chunk(
        get_stream_writer(),
        sub_agent_call_event(
            SubAgentCallPayload(
                tool_call_id=tool_call_id,
                sub_agent=_EDIT_ROLE,
                phase=WIRE_PHASE_BY_ROLE[_EDIT_ROLE],
                state=state,
                model_id=sub_agent_model_id(_EDIT_TOOL),
                summary=summary,
                succeeded=None if state == "started" else state == "completed",
                tokens=spent.tokens,
                cost_usd=str(spent.cost),
            ),
        ),
    )


async def propose_changes(
    ctx: RunContext[LeadDeps], proposal: CardProposal
) -> EditDelta:
    """Offer the researcher further work on the strategy, as a card they answer.

    Every reply that would end by offering work - a refinement, a stricter
    filter, one way rather than another - ends with this call instead of a
    question. The reply is this call's ``reply``: it streams above the card,
    so write the whole answer to the message there and nothing as text.
    The researcher answers Yes or No and can add a comment. A yes runs the edit
    with ``proposedChanges`` and the comment as its brief, and the ``EditDelta``
    comes back here: report it as after any ``edit_strategy``. On a conversation
    with no strategy yet, a yes asks you to frame and build the changes. A no
    ends the turn with your text as it stands, so never ask the offer in prose.
    Never offer a sweep, a separation or a control test on this card: its yes
    runs an edit of the strategy. Call that tool itself; its own approval is
    the card.
    """
    deps = ctx.deps
    tool_call_id = dispatch_call_id(ctx)
    deps.state.turn_markers.accepted_proposal = True
    deps.state.domain.declined_proposal = None
    brief = accepted_brief(deps.state, tool_call_id, proposal)
    if not deps.step_count:
        raise ModelRetry(nothing_to_edit_message(brief))
    _edit_card(deps, tool_call_id, "started", proposal.question)
    try:
        result = await run_edit(
            deps=deps, parent_tool_call_id=tool_call_id, reason=brief
        )
    except ModelRetry as refusal:
        _edit_card(deps, tool_call_id, "failed", refusal.message)
        raise
    if isinstance(result, SubAgentApprovalWait):
        defer_dispatch(deps, tool_call_id, result)
    _edit_card(deps, tool_call_id, "completed", result.description)
    return result


__all__ = ["accepted_brief", "propose_changes"]
