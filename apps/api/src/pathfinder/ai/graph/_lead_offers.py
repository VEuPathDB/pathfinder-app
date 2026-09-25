"""What the researcher did with a card the Lead parked, and the card a no closes.

A card is an offer (a proposal of further work or a measured strategy to
adopt), a question, or a call that asks before it runs. A yes runs the call. A
no on an offer ends the turn with no model call, and a no on any other card is
the denial the run resumes with. A typed message declines any card and reaches
the Lead as the next message.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from assistant_core.graph import approvals
from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.turn_state import ParkedCall, PendingApproval
from pydantic_ai.tools import (
    DeferredToolApprovalResult,
    DeferredToolResults,
    ToolDenied,
)
from pydantic_ai.ui.vercel_ai.response_types import (
    ToolInputAvailableChunk,
    ToolInputStartChunk,
    ToolOutputDeniedChunk,
)

from pathfinder.ai.graph._lead_answers import answers_for, is_pure_approval, typed_reply
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.proposal import (
    OFFER_TOOLS,
    PROPOSAL_TOOL,
    AdoptionArgs,
    DeclinedProposal,
)

_DECLINED_BY_REPLY = "The researcher sent a new message instead of answering the card."
# A no on a removal is a no to the message that asked for it.
_REMOVAL_CARDS = frozenset({"delete_step", "clear_strategy"})
# A question card is answered with its answers, so a typed yes answers nothing.
_QUESTION_CARD = "consult_user"


@dataclass(frozen=True)
class OfferAnswer:
    """The researcher's answer to a card, as the resumed run takes it.

    ``results`` answer the parked call; a declined offer re-enters nothing; a
    card with no answer yet keeps waiting.
    """

    results: DeferredToolResults | None = None
    declined: bool = False
    pending: bool = False
    user_prompt: str | None = None


def _declined_offer(
    domain: StrategyDomainState, approval: PendingApproval, note: str
) -> DeclinedProposal | None:
    """The card as the ledger lists it once declined, or None for an offer it lacks."""
    if approval.tool_name == PROPOSAL_TOOL:
        return DeclinedProposal.model_validate({**approval.tool_args, "note": note})
    task_id = AdoptionArgs.model_validate(approval.tool_args).task_id
    offer = domain.separation_offers.get(task_id)
    if offer is None:
        return None
    return DeclinedProposal(
        question=offer.question,
        proposed_changes=[
            f"{criterion.text} ({criterion.role})" for criterion in offer.spec.criteria
        ],
        note=note,
    )


def _record_the_decline(
    domain: StrategyDomainState, approval: PendingApproval, note: str
) -> None:
    """Record the offer the researcher declined, until a later card is accepted.

    A declined separation keeps its offer, so a later turn can build it.
    """
    domain.declined_proposal = _declined_offer(domain, approval, note)


def _typed_yes(approval: PendingApproval, typed: str | None) -> bool:
    """Whether the typed message accepts the card as a click on yes would."""
    return (
        typed is not None
        and approval.tool_name != _QUESTION_CARD
        and is_pure_approval(typed)
    )


def answer_to_the_offer(
    state: PipelineState, domain: StrategyDomainState, approval: PendingApproval
) -> OfferAnswer:
    """A yes runs the card's call. A no on an offer ends the turn with no model
    call, and a no on any other card resumes the run with the denial.

    A typed approval phrase is a yes, except on a question card. Any other
    typed message declines the card and is delivered to the Lead as the
    researcher's next message. ``state`` is the turn the answer arrived on;
    ``domain`` is the record the run writes.
    """
    answer: bool | DeferredToolApprovalResult | None = answers_for(
        state, [approval.tool_call_id]
    ).get(approval.tool_call_id)
    typed = typed_reply(state)
    if answer is None and _typed_yes(approval, typed):
        answer = True
    offer = approval.tool_name in OFFER_TOOLS
    if (
        answer is not None
        and answer is not True
        and approval.tool_name in _REMOVAL_CARDS
    ):
        domain.withdraw_this_messages_requirements()
    if answer is True or (answer is not None and not offer):
        return OfferAnswer(
            results=DeferredToolResults(approvals={approval.tool_call_id: answer}),
        )
    if answer is not None:
        response = state.approval_responses[approval.tool_call_id]
        _record_the_decline(domain, approval, response.reason or "")
        return OfferAnswer(declined=True)
    if typed is None:
        return OfferAnswer(pending=True)
    if offer:
        _record_the_decline(domain, approval, "")
    denial: DeferredToolApprovalResult = ToolDenied(message=_DECLINED_BY_REPLY)
    return OfferAnswer(
        results=DeferredToolResults(approvals={approval.tool_call_id: denial}),
        user_prompt=typed,
    )


def close_the_declined_card(
    parked: ParkedCall | None,
    capture: _LeadRunCapture,
    writer: Any,
) -> None:
    """Close the card as denied with no model call.

    The reply already on screen stays the turn's reply, so the turn leaves its
    answer and its questions as they stood.
    """
    if parked is None:
        return
    hint = approvals.deferred_hint(parked)
    for chunk in (
        ToolInputStartChunk(tool_call_id=hint.tool_call_id, tool_name=hint.tool_name),
        ToolInputAvailableChunk(
            tool_call_id=hint.tool_call_id,
            tool_name=hint.tool_name,
            input=hint.tool_args,
        ),
        ToolOutputDeniedChunk(tool_call_id=hint.tool_call_id),
    ):
        emit_chunk(writer, chunk)
    capture.parked_call_answered = True
    capture.offer_declined = True


__all__ = [
    "OfferAnswer",
    "answer_to_the_offer",
    "close_the_declined_card",
]
