"""The turn contract for a turn that ends on a card.

The reply is the text the Lead wrote beside the card's call, and it is held to
the same record as a typed reply before the card reaches the researcher.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic_ai import RunContext
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.tools import (
    DeferredToolApprovalResult,
    DeferredToolRequests,
    DeferredToolResults,
    ToolDenied,
)

from pathfinder.ai.lead.proposal import PROPOSAL_TOOL
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    PROSE_MAX_CHARS,
    LeadResponse,
    correction_for,
    reconcile,
)
from pathfinder.ai.lead.turn_record import turn_record

CARD_TOOLS: frozenset[str] = frozenset({"consult_user", PROPOSAL_TOOL})

_NOT_SHOWN = "The card was not shown to the researcher. Answer again with the card."


def reply_beside_the_card(messages: Sequence[ModelMessage]) -> str:
    """The text of the response that made the card's call."""
    response = next(
        (m for m in reversed(messages) if isinstance(m, ModelResponse)), None
    )
    if response is None:
        return ""
    text = "".join(p.content for p in response.parts if isinstance(p, TextPart))
    return text[:PROSE_MAX_CHARS]


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
    record = turn_record(ctx).model_copy(update={"ends_on_a_card": True})
    report = LeadResponse(
        prose=reply_beside_the_card(ctx.messages),
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


__all__ = ["CARD_TOOLS", "hold_the_contract_on_a_card", "reply_beside_the_card"]
