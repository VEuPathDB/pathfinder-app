"""After a check of this turn, the strategy changes only through a card.

A finding about what the records show is the researcher's to act on, so the
tools that write are withdrawn and the proposal card stays. A finding about
the tree is the build's to fix, so the tools that write stay.
"""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import (
    FailureCause,
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS, tools_the_turn_offers
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
    user_intent,
)

_WRITERS = BUILDING_TOOLS - {"verify_strategy"}
_NAMES = BUILDING_TOOLS | {PROPOSAL_TOOL}


def _digest(*, success: bool, cause: FailureCause | None = None) -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="Sampled 8 records.",
        reason="The sample was read.",
        success=success,
        failure_cause=cause,
    )


def _deps() -> LeadDeps:
    state = pipeline_state(
        user_prompt="genes with a Rab GTPase annotation",
        user_message_id=uuid4(),
        domain=StrategyDomainState(),
    )
    state.turn_markers.intent_classified = True
    state.turn_markers.built = True
    return lead_deps(
        state,
        intent=user_intent(IntentClassification.NEW_STRATEGY),
        strategy_session=session_with_one_step(),
    )


def _checked(digest: VerificationDigest) -> LeadDeps:
    deps = _deps()
    domain = deps.state.domain
    domain.record_verdict(digest, revision=strategy_revision(domain.answered_graph))
    deps.state.turn_markers.verification_dispatched = True
    deps.state.turn_markers.verified = digest.passed
    return deps


def _offered(deps: LeadDeps) -> frozenset[str]:
    return tools_the_turn_offers(deps, _NAMES)


def test_a_passed_check_offers_the_card_and_no_edit() -> None:
    offered = _offered(_checked(_digest(success=True)))

    assert PROPOSAL_TOOL in offered
    assert not offered & _WRITERS


def test_a_check_failed_on_the_records_offers_the_card_and_no_edit() -> None:
    offered = _offered(_checked(_digest(success=False)))

    assert offered == {PROPOSAL_TOOL, "verify_strategy"}


def test_a_check_failed_on_the_tree_offers_the_edit() -> None:
    deps = _checked(_digest(success=False, cause=FailureCause.STRUCTURE_VIOLATION))

    assert {"edit_strategy", "verify_strategy", PROPOSAL_TOOL} <= _offered(deps)


def test_a_fix_of_the_tree_waits_for_the_next_check() -> None:
    """The verdict judged the tree before the fix, so it opens no second edit."""
    deps = _checked(_digest(success=False, cause=FailureCause.STRUCTURE_VIOLATION))
    deps.state.domain.verified_revision = "an earlier tree"

    assert _offered(deps) & BUILDING_TOOLS == {"verify_strategy"}


def test_a_check_that_stopped_offers_no_edit() -> None:
    deps = _deps()
    deps.state.turn_markers.verification_dispatched = True
    deps.state.turn_markers.verification_stopped = True

    assert _offered(deps) == {PROPOSAL_TOOL, "verify_strategy"}


def test_a_turn_with_no_check_offers_the_edit() -> None:
    offered = _offered(_deps())

    assert {"edit_strategy", "verify_strategy", PROPOSAL_TOOL} <= offered


def test_a_refused_reply_after_a_tree_failure_reaches_only_the_check() -> None:
    """The refusal and the card rule each withdraw tools; neither adds one."""
    deps = _checked(_digest(success=False, cause=FailureCause.STRUCTURE_VIOLATION))
    deps.state.turn_markers.contract_refused = True

    assert _offered(deps) == {PROPOSAL_TOOL, "verify_strategy"}


def test_a_new_message_starts_without_the_check() -> None:
    deps = _checked(_digest(success=True))
    deps.state.user_message_id = uuid4()
    deps.state.turn_markers.intent_classified = True

    assert "edit_strategy" in _offered(deps)


_CARD_RULE = (
    "The strategy changes only through a card this turn: offer any change "
    "with propose_changes showing the count before and after it, or report "
    "the finding and ask."
)


def test_a_records_finding_tells_the_lead_the_change_takes_a_card() -> None:
    dumped = VerificationDelta(digest=_digest(success=False)).model_dump(
        by_alias=True, mode="json"
    )

    assert dumped["nextStep"] == _CARD_RULE


def test_a_pass_tells_the_lead_the_change_takes_a_card() -> None:
    dumped = VerificationDelta(digest=_digest(success=True)).model_dump(
        by_alias=True, mode="json"
    )

    assert dumped["nextStep"] == _CARD_RULE


def test_a_tree_finding_leaves_the_fix_to_the_build() -> None:
    delta = VerificationDelta(
        digest=_digest(success=False, cause=FailureCause.STRUCTURE_VIOLATION)
    )

    assert [delta.model_dump(by_alias=True, mode="json")["nextStep"]] == [None]


def test_the_next_step_is_not_asked_of_the_checker() -> None:
    """The runtime derives it, so the sub-agent's output schema omits it."""
    schema = VerificationDelta.model_json_schema(mode="validation")

    assert "nextStep" not in schema["properties"]
