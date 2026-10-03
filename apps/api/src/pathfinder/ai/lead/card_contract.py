"""The turn contract for a turn that ends on a card.

The reply is the ``reply`` argument of the card's call, and it is held to the
same record as a typed reply before the card reaches the researcher.
"""

from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.tools import (
    DeferredToolApprovalResult,
    DeferredToolRequests,
    DeferredToolResults,
    ToolDenied,
)

from pathfinder.ai.lead.card_reply import PROSE_MAX_CHARS, CardCallReply
from pathfinder.ai.lead.deleted_steps import DELETE_TOOL
from pathfinder.ai.lead.proposal import OFFER_TOOLS
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    LeadResponse,
    correction_for,
    to_correct,
)
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.tools.standalone.optimization import PARAMETER_SWEEP
from pathfinder.ai.tools.standalone.separation import SEPARATION

# The calls that end a turn on a card, each carrying the turn's reply.
CARD_TOOLS: frozenset[str] = frozenset(
    {
        "consult_user",
        "clear_strategy",
        DELETE_TOOL,
        PARAMETER_SWEEP.tool_name,
        SEPARATION.tool_name,
        *OFFER_TOOLS,
    }
)

_NOT_SHOWN = "The card was not shown to the researcher. Answer again with the card."


def _replies_beside_the_cards(requests: DeferredToolRequests) -> list[str]:
    """The replies the card calls of one response carry, in call order."""
    replies = (
        CardCallReply.model_validate(call.args_as_dict()).reply
        for call in requests.approvals
        if call.tool_name in CARD_TOOLS
    )
    return [reply for reply in replies if reply]


def hold_the_contract_on_a_card(
    ctx: RunContext[LeadDeps],
    requests: DeferredToolRequests,
) -> DeferredToolResults | None:
    """Deny every card of a response whose replies do not match the turn. The
    correction returns inside the same run, and the corrected answer issues
    the card again."""
    cards = [
        call.tool_call_id for call in requests.approvals if call.tool_name in CARD_TOOLS
    ]
    if not cards:
        return None
    record = turn_record(ctx).model_copy(update={"ends_on_a_card": True})
    replies = _replies_beside_the_cards(requests)
    report = LeadResponse(
        prose="\n\n".join(replies)[:PROSE_MAX_CHARS],
        strategy_changed=record.changed_strategy,
    )
    mismatches = to_correct(ctx, report, record, replies)
    if not mismatches:
        return None
    denial: DeferredToolApprovalResult = ToolDenied(
        message=f"{correction_for(mismatches)}\n\n{_NOT_SHOWN}",
    )
    return DeferredToolResults(approvals=dict.fromkeys(cards, denial))


__all__ = ["CARD_TOOLS", "hold_the_contract_on_a_card"]
