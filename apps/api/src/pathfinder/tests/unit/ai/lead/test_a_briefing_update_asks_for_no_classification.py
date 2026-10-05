"""A briefing update that follows a tool result is no researcher message, so the
Lead classifies once per message and the held intent orders nothing."""

from __future__ import annotations

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.lead_pins import pinned_user_intent
from pathfinder.tests._support.run_context import lead_run_context


def test_the_lead_classifies_once_per_researcher_message() -> None:
    read = " ".join(LEAD_INSTRUCTIONS.split())

    assert "Call ``classify_user_intent`` once per researcher message" in read
    assert (
        "A briefing update that follows a tool result is not a message, and it "
        "never asks for a classification."
    ) in read


def test_an_unclassified_intent_orders_no_call() -> None:
    assert (
        pinned_user_intent(lead_run_context()) == "## User Intent\nNot classified yet."
    )
