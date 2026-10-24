from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    user_intent,
)

_COMPLETE = "The model audit is complete. Both gene models are judged incorrect."


def _audit_turn() -> LeadDeps:
    state = pipeline_state(user_prompt="Audit the two gene models.")
    state.user_message_id = uuid4()
    state.turn_markers.intent_classified = True
    return lead_deps(state, intent=user_intent(IntentClassification.GENE_MODEL_AUDIT))


def test_a_reply_that_claims_an_audit_with_no_run_is_refused() -> None:
    deps = _audit_turn()

    [sentence] = [
        m.sentence
        for m in reconcile(reply(_COMPLETE), turn_record(run_context_for(deps)))
        if m.kind == "claimed_audit_run"
    ]

    assert sentence == (
        "The reply says an audit ran, and this turn started no audit run and read "
        "none. Say what the turn did: what the investigator judged, or that no "
        "audit started and why."
    )


def test_a_reply_about_a_run_the_turn_read_stands() -> None:
    deps = _audit_turn()
    deps.state.turn_markers.record_audit_runs([uuid4()])

    assert "claimed_audit_run" not in kinds(deps, reply(_COMPLETE))


def test_a_reply_that_says_no_audit_ran_stands() -> None:
    prose = "No audit run has started: the planner holds no genome by that name."

    assert "claimed_audit_run" not in kinds(_audit_turn(), reply(prose))
