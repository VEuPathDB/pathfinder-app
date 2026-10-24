from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.caveats import RequirementGap
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    kinds,
    reading_deps,
    reply,
)
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


def _over_a_failed_check(deps: LeadDeps) -> LeadDeps:
    domain = deps.state.domain
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="The site serves no search for split genes.",
            success=False,
            gaps=[RequirementGap(text="split genes", status="unmet")],
        ),
        revision=strategy_revision(domain.answered_graph),
    )
    return deps


def test_an_audit_turn_owes_no_word_on_the_strategys_failed_check() -> None:
    deps = _over_a_failed_check(_audit_turn())
    deps.state.turn_markers.record_audit_runs([uuid4()])

    assert kinds(deps, reply("The audit found three error patterns.")) == []


def test_a_strategy_turn_still_states_the_failed_check() -> None:
    deps = _over_a_failed_check(reading_deps())

    assert kinds(deps, reply("The strategy returns the genes.")) == ["failed_check"]


def test_a_reply_that_says_no_audit_ran_stands() -> None:
    prose = "No audit run has started: the planner holds no genome by that name."

    assert "claimed_audit_run" not in kinds(_audit_turn(), reply(prose))
