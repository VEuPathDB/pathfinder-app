from __future__ import annotations

from decimal import Decimal

from assistant_core.platform.types import PaidBy

from pathfinder.ai.graph._lead_capture import _LeadRunCapture, absorb_outside_spend


def test_decisions_spend_counts_outside_the_lead_and_on_the_payer() -> None:
    capture = _LeadRunCapture()

    absorb_outside_spend(capture, 700, Decimal("0.00007"), PaidBy.DEPLOYMENT)
    absorb_outside_spend(capture, 300, Decimal("0.00003"), PaidBy.USER)

    spend = capture.spend_outside_the_lead()
    assert (
        spend.sub_agent_tokens,
        spend.sub_agent_cost,
        spend.own_key_tokens,
        spend.own_key_cost,
    ) == (
        1000,
        Decimal("0.00010"),
        300,
        Decimal("0.00003"),
    )
    assert capture.billed_outside_the_lead.sub_agent_tokens == 0
