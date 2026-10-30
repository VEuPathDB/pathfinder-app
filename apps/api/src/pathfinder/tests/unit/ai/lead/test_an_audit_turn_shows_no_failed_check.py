from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.caveats import RequirementGap
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reading_deps
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
            gaps=[RequirementGap(text="split genes")],
        ),
        revision=strategy_revision(domain.answered_graph),
    )
    return deps


def test_an_audit_turn_shows_no_failure_of_the_strategys_check() -> None:
    deps = _over_a_failed_check(_audit_turn())

    assert turn_facts(deps).failed_check == ""


def test_a_strategy_turn_still_shows_the_failed_check() -> None:
    deps = _over_a_failed_check(reading_deps())

    assert turn_facts(deps).failed_check == (
        "The last check of this strategy failed: The site serves no search for "
        "split genes."
    )
