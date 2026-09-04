"""How an early stop reads, and how far it travels."""

from __future__ import annotations

from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state


def _budget_stop() -> PhaseStop:
    return PhaseStop(
        role="frame",
        reason=PhaseStopReason.BUDGET,
        tool_calls=60,
        criteria_bound=3,
        criteria_declared=8,
    )


def test_a_repetition_stop_renders_without_criteria_counts() -> None:
    stop = PhaseStop(
        role="verification",
        reason=PhaseStopReason.REPEATED_CALL,
        tool_calls=12,
    )

    assert stop.render() == (
        "the verification pass stopped after repeating one call after 12 calls"
    )


def test_the_ledger_the_lead_reads_names_the_stop() -> None:
    summary = derive_ledger(
        pipeline_state(user_prompt="Find the kinases."),
        None,
        phase_stop=_budget_stop(),
    ).render_summary()

    assert (
        "- stopped: the framing pass stopped on its call budget after 60 calls "
        "with 3 of 8 criteria bound" in summary
    )


def test_a_ledger_snapshot_keeps_the_stop_off_the_wire() -> None:
    stop = PhaseStop(role="frame", reason=PhaseStopReason.BUDGET, tool_calls=60)
    ledger = derive_ledger(pipeline_state(), None, phase_stop=stop)

    dumped = ledger.model_dump(by_alias=True, mode="json", exclude_none=True)

    assert "phaseStop" not in dumped
