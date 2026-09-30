"""The refusal of a reply that leaves out the change names what the turn built."""

from __future__ import annotations

from pathfinder.ai.lead.contract_messages import unreported_change_message
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.turn_facts import StepFact, TurnFacts

# The hostdb conversation: two searches and their INTERSECT, built this turn.
_BUILT = TurnFacts(
    steps=[
        StepFact(step_id="step_loc", display_name="Genomic Location", count=2268),
        StepFact(step_id="step_go", display_name="GO Term", count=412),
        StepFact(step_id="step_and", display_name="Intersect", operator="INTERSECT"),
    ],
    root_count=9,
)


def test_the_refusal_names_each_step_the_turn_built_and_the_root() -> None:
    outcome = BuildOutcome(pushed_step_ids=["step_loc", "step_go", "step_and"])

    message = unreported_change_message(outcome, _BUILT)

    assert "it built Genomic Location, GO Term, Intersect" in message
    assert "root holds 9" in message
    assert "never that nothing changed" in message


def test_a_turn_that_pushed_no_step_names_no_built_step() -> None:
    message = unreported_change_message(None, _BUILT)

    assert "built" not in message.split(".")[0]
    assert "root holds 9" in message
