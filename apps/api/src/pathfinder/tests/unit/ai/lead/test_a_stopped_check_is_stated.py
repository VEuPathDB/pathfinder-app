"""A reply after a check that stopped says the check did not finish."""

from __future__ import annotations

from dataclasses import replace

from pathfinder.ai.lead.phase_stop import PhaseStop, PhaseStopReason
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    reading_deps,
    reply,
)

A_CAP_STOP = PhaseStop(
    role="verification",
    reason=PhaseStopReason.CALL_CAP,
    tool_calls=11,
    tool_name="read_gene_record",
)
A_FRAME_STOP = PhaseStop(
    role="frame",
    reason=PhaseStopReason.BUDGET,
    tool_calls=60,
    criteria_bound=3,
    criteria_declared=8,
)
OMITS_THE_STOP = "I added the essentiality filter to the strategy."
STATES_THE_STOP = (
    "I added the essentiality filter. The Verification-pass STOPPED past its "
    "read budget before it finished, so the strategy is not verified yet."
)


def _built_and_stopped() -> LeadDeps:
    """A turn that pushed a build, dispatched its check, and the check stopped."""
    deps = building_deps(verified=False)
    markers = deps.state.turn_markers
    markers.verification_dispatched = True
    markers.verification_stopped = True
    deps.last_phase_stop = A_CAP_STOP
    return deps


def _mismatches(deps: LeadDeps, report: LeadResponse) -> list[tuple[str, str]]:
    record = turn_record(replace(run_context_for(deps), retries={}))
    return [(m.kind, m.sentence) for m in reconcile(report, record)]


def test_a_built_turn_whose_check_stopped_is_refused_until_it_says_so() -> None:
    found = _mismatches(_built_and_stopped(), reply(OMITS_THE_STOP, changed=True))

    assert [kind for kind, _ in found] == ["stopped_check"]
    assert A_CAP_STOP.render() in found[0][1]


def test_a_reply_that_states_the_stop_in_any_case_or_hyphenation_passes() -> None:
    found = _mismatches(_built_and_stopped(), reply(STATES_THE_STOP, changed=True))

    assert found == []


def test_a_stopped_frame_pass_is_held_by_the_unfinished_work_rule_alone() -> None:
    deps = reading_deps()
    deps.last_phase_stop = A_FRAME_STOP

    found = _mismatches(deps, reply(OMITS_THE_STOP))

    assert [kind for kind, _ in found] == ["unfinished_work"]
