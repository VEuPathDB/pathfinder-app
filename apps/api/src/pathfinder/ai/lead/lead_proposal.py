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
from pathfinder.ai.lead.card_reply import CARD_NOT_SHOWN
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
from pathfinder.domain.strategy.card_coverage import uncovered_requirements
from pathfinder.domain.strategy.constraints import ConstraintSource

_EDIT_TOOL = "edit_strategy"
_EDIT_ROLE = "frame"


def accepted_note(state: PipelineState, tool_call_id: str) -> str:
    """The note the researcher sent with the yes; the card's words are the Lead's."""
    answers = state.user_question_answers.get(tool_call_id, [])
    return " ".join(answer.note for answer in answers if answer.note)


def accepted_brief(state: PipelineState, tool_call_id: str, proposal: Proposal) -> str:
    """The edit's brief: the card's changes and the note sent with the yes."""
    return proposal.brief(accepted_note(state, tool_call_id))


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


def refuse_a_card_that_leaves_a_part(
    ctx: RunContext[LeadDeps], proposal: CardProposal
) -> None:
    """Refuse a card that names a key the thread does not hold, or that leaves a
    requirement this message states with no change and no question.

    A requirement the strategy already holds needs neither. The check holds the
    card before the researcher reads it, so a card they accepted runs as accepted.
    """
    if ctx.tool_call_approved:
        return
    state = ctx.deps.state
    held = {c.key: c for c in state.domain.requirements}
    named = proposal.named_keys()
    unknown = [key for key in named if key not in held]
    stated = [
        c
        for c in state.turn_markers.requirements_added
        if c.key in held and c.source is ConstraintSource.USER_EXPLICIT
    ]
    left = uncovered_requirements(
        stated,
        named=named,
        held=list(held.values()),
        spec=state.domain.operational_spec,
        marks=state.domain.data_marks,
    )
    if not unknown and not left:
        return
    problems = []
    if unknown:
        keys = ", ".join(held) or "none"
        problems.append(
            f"These keys name no requirement the conversation holds: "
            f"{', '.join(unknown)}. The keys it holds are: {keys}."
        )
    if left:
        parts = ", ".join(f'"{c.label}" ({c.key})' for c in left)
        problems.append(
            f"The card leaves these requirements of this message with no change "
            f"and no question: {parts}. Add a change that answers each one and "
            f"name its key in that change's answers, or name the key in "
            f"leftToAsk and ask about it in the reply."
        )
    raise ModelRetry(" ".join([*problems, CARD_NOT_SHOWN]))


async def propose_changes(
    ctx: RunContext[LeadDeps], proposal: CardProposal
) -> EditDelta:
    """Offer the researcher further work on the strategy, as a card they answer.

    Every reply that would end by offering work - a refinement, a stricter
    filter, one way rather than another - ends with this call instead of a
    question. The reply is this call's ``reply``: it streams above the card,
    so write the whole answer to the message there and nothing as text.
    Each change is typed by what it binds: values set on a criterion the
    ledger lists, or a criterion added with the search it runs. Each change
    names in ``answers`` the key of each requirement it answers, and
    ``leftToAsk`` names each requirement of this message that no change
    answers and the reply asks about. A card that leaves out a requirement
    this message states is refused, naming it; one the strategy already holds
    needs no change. A removal is ``delete_step``, whose card lists what it
    removes. The researcher answers
    Yes or No and can add a comment. A yes records the comment as the
    researcher's words and runs the edit with ``proposedChanges`` and the
    comment as its brief, and the ``EditDelta``
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
    deps.state.domain.record_request_text(accepted_note(deps.state, tool_call_id))
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


__all__ = ["accepted_brief", "propose_changes", "refuse_a_card_that_leaves_a_part"]
