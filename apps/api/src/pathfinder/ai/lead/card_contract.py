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
from pathfinder.ai.lead.proposal import ADOPT_TOOL, OFFER_TOOLS, AdoptionArgs
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    LeadResponse,
    correction_for,
    reconcile,
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


def _reply_beside_the_card(requests: DeferredToolRequests) -> str:
    """The replies the card calls of one response carry, in call order."""
    replies = [
        CardCallReply.model_validate(call.args_as_dict()).reply
        for call in requests.approvals
        if call.tool_name in CARD_TOOLS
    ]
    return "\n\n".join(reply for reply in replies if reply)[:PROSE_MAX_CHARS]


def hold_the_contract_on_a_card(
    ctx: RunContext[LeadDeps],
    requests: DeferredToolRequests,
) -> DeferredToolResults | None:
    """Deny a card whose reply does not match the turn, with the correction.

    The denial returns the correction to the Lead inside the same run, so the
    card is never emitted and the corrected answer issues it again. It is asked
    once per turn, on the same latch as the typed reply's correction.
    """
    cards = [
        call.tool_call_id for call in requests.approvals if call.tool_name in CARD_TOOLS
    ]
    markers = ctx.deps.state.turn_markers
    if not cards or markers.contract_refused:
        return None
    adoptions = [
        AdoptionArgs.model_validate(call.args_as_dict()).task_id
        for call in requests.approvals
        if call.tool_name == ADOPT_TOOL
    ]
    record = turn_record(ctx, card_offer=next(iter(adoptions), None)).model_copy(
        update={"ends_on_a_card": True}
    )
    report = LeadResponse(
        prose=_reply_beside_the_card(requests),
        strategy_changed=record.changed_strategy,
    )
    mismatches = reconcile(report, record)
    if not mismatches:
        return None
    markers.contract_refused = True
    denial: DeferredToolApprovalResult = ToolDenied(
        message=f"{correction_for(mismatches)}\n\n{_NOT_SHOWN}",
    )
    return DeferredToolResults(approvals=dict.fromkeys(cards, denial))


__all__ = ["CARD_TOOLS", "hold_the_contract_on_a_card"]
