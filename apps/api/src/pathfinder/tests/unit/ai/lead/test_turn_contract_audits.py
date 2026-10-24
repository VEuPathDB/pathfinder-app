from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
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


def _audit_turn() -> LeadDeps:
    state = pipeline_state(user_prompt="Audit the two gene models.")
    state.user_message_id = uuid4()
    state.turn_markers.intent_classified = True
    return lead_deps(state, intent=user_intent(IntentClassification.GENE_MODEL_AUDIT))


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


def test_the_record_says_which_turn_is_an_audit() -> None:
    assert (
        turn_record(run_context_for(_audit_turn())).audit_turn,
        turn_record(run_context_for(reading_deps())).audit_turn,
    ) == (True, False)


def test_an_audit_turn_owes_no_word_on_the_strategys_failed_check() -> None:
    deps = _over_a_failed_check(_audit_turn())

    assert kinds(deps, reply("The audit found three error patterns.")) == []


def test_a_strategy_turn_still_states_the_failed_check() -> None:
    deps = _over_a_failed_check(reading_deps())

    assert kinds(deps, reply("The strategy returns the genes.")) == ["failed_check"]
