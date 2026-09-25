"""A typed answer to a card reaches the card's tool before any classification."""

from __future__ import annotations

from assistant_core.graph.turn_state import PendingApproval, SubAgentApprovalPending

from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_NAMES = [
    "classify_user_intent",
    "delete_step",
    "clear_strategy",
    "recover_failed_steps",
]


def _answering(card: PendingApproval) -> LeadDeps:
    state = pipeline_state(user_prompt="yes")
    state.pending_approval = card
    return lead_deps(state)


def test_the_card_a_typed_answer_resumes_is_reachable_unclassified() -> None:
    deps = _answering(
        PendingApproval(phase="lead", tool_call_id="call_1", tool_name="delete_step")
    )

    assert tools_the_turn_offers(deps, _NAMES) == {
        "classify_user_intent",
        "delete_step",
    }


def test_a_sub_agent_card_leaves_its_dispatch_to_the_classification() -> None:
    deps = _answering(
        PendingApproval(
            phase="execution",
            tool_call_id="call_1",
            tool_name="recover_failed_steps",
            sub_agent=SubAgentApprovalPending(role="execution"),
        )
    )

    assert tools_the_turn_offers(deps, _NAMES) == {"classify_user_intent"}


def test_a_turn_with_no_card_reaches_only_the_unclassified_tools() -> None:
    deps = lead_deps(pipeline_state(user_prompt="yes"))

    assert tools_the_turn_offers(deps, _NAMES) == {"classify_user_intent"}
