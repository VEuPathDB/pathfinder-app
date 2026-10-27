"""A briefing update that follows a tool result is no researcher message, so the
Lead classifies once per message and the held intent orders nothing."""

from __future__ import annotations

from pathfinder.ai.lead.lead_pins import pinned_user_intent
from pathfinder.tests._support.run_context import lead_run_context


def test_an_unclassified_intent_orders_no_call() -> None:
    assert (
        pinned_user_intent(lead_run_context()) == "## User Intent\nNot classified yet."
    )
