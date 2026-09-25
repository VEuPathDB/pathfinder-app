"""A card the Lead parks takes a typed message the way an offer card does."""

from __future__ import annotations

from uuid import uuid4

import pytest
from assistant_core.graph.approvals import DENIED_WITHOUT_REASON
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai.tools import DeferredToolResults, ToolDenied
from pydantic_ai.ui.vercel_ai.request_types import ToolApprovalResponded

from pathfinder.ai.graph._lead_offers import OfferAnswer, answer_to_the_offer
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.tests.unit.ai.lead.conftest import user_intent

CALL_ID = "call_card"
TYPED = "Keep the strategy and add a GO filter instead."
DECLINED_BY_REPLY = "The researcher sent a new message instead of answering the card."


def _parked(tool_name: str) -> PipelineState:
    asked_under = uuid4()
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_message_id=asked_under,
        pending_approval=PendingApproval(
            phase="lead",
            tool_call_id=CALL_ID,
            tool_name=tool_name,
            user_message_id=asked_under,
        ),
    )


def _typed(tool_name: str, text: str) -> PipelineState:
    state = _parked(tool_name)
    state.user_message_id = uuid4()
    state.user_prompt = text
    return state


def _answer(state: PipelineState) -> OfferAnswer:
    assert state.pending_approval is not None
    return answer_to_the_offer(state, state.domain, state.pending_approval)


def _denied(message: str) -> DeferredToolResults:
    return DeferredToolResults(approvals={CALL_ID: ToolDenied(message=message)})


@pytest.mark.parametrize("tool_name", ["clear_strategy", "delete_step", "consult_user"])
def test_a_typed_message_declines_the_card_and_is_delivered(tool_name: str) -> None:
    state = _typed(tool_name, TYPED)

    answer = _answer(state)

    assert answer == OfferAnswer(results=_denied(DECLINED_BY_REPLY), user_prompt=TYPED)
    assert state.domain.declined_proposal is None


@pytest.mark.parametrize("tool_name", ["clear_strategy", "delete_step"])
def test_a_typed_yes_approves_a_card_that_asks_before_it_runs(tool_name: str) -> None:
    answer = _answer(_typed(tool_name, "Yes, go ahead."))

    assert answer == OfferAnswer(
        results=DeferredToolResults(approvals={CALL_ID: True}),
    )


def test_a_typed_yes_does_not_answer_a_question_card() -> None:
    answer = _answer(_typed("consult_user", "yes"))

    assert answer == OfferAnswer(results=_denied(DECLINED_BY_REPLY), user_prompt="yes")


@pytest.mark.parametrize("tool_name", ["clear_strategy", "consult_user"])
def test_a_clicked_no_resumes_the_run_with_the_denial(tool_name: str) -> None:
    state = _parked(tool_name)
    state.approval_responses = {
        CALL_ID: ToolApprovalResponded(id=CALL_ID, approved=False),
    }

    answer = _answer(state)

    assert answer == OfferAnswer(results=_denied(DENIED_WITHOUT_REASON))
    assert state.domain.declined_proposal is None


def test_a_card_with_no_answer_keeps_waiting() -> None:
    assert _answer(_parked("clear_strategy")) == OfferAnswer(pending=True)


@pytest.mark.parametrize("tool_name", ["clear_strategy", "delete_step"])
def test_a_clicked_no_on_a_removal_withdraws_what_its_message_asked(
    tool_name: str,
) -> None:
    earlier = Constraint(
        kind=ConstraintKind.ORGANISM,
        label="organism",
        requested_value="Plasmodium falciparum 3D7",
    )
    asked = Constraint(
        kind=ConstraintKind.OTHER,
        label="removal",
        requested_value="Delete the intersection step",
    )
    state = _parked(tool_name)
    state.domain.record_requirements([earlier])
    state.domain.markers_for(state.user_message_id)
    state.domain.record_intent(
        user_intent(IntentClassification.EDIT_STRATEGY, explicit_constraints=[asked]),
        request_text="Delete the intersection step but keep both searches.",
    )
    state.approval_responses = {
        CALL_ID: ToolApprovalResponded(id=CALL_ID, approved=False),
    }

    _answer(state)

    assert [c.requested_value for c in state.domain.requirements] == [
        "Plasmodium falciparum 3D7"
    ]
