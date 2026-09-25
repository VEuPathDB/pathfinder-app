"""The Lead reads when to run a separation and how to offer what it found."""

from __future__ import annotations

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS


def test_the_sweep_rule_names_the_reverse_direction() -> None:
    assert (
        "The reverse, controls and no strategy yet, is ``separate_controls``."
        in LEAD_INSTRUCTIONS
    )


def test_the_separation_rule_offers_the_result_on_its_card() -> None:
    assert (
        "call ``adopt_separating_strategy`` with the report's task id and a "
        "``reply`` written from its counts" in " ".join(LEAD_INSTRUCTIONS.split())
    )
    assert "Never state a count the report does not hold." in LEAD_INSTRUCTIONS
