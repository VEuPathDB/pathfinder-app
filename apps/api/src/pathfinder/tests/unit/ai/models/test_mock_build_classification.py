"""The mock reads a build over a framed draft as extending it."""

from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.models.mock.reading import scripted_intent
from pathfinder.domain.exchanges import Exchange
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests.unit.ai.lead._answered_draft import framed
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_BUILD = "Find protein kinases in P. falciparum 3D7. [[arc:single]]"
_CONSULT = "Consult me before planning this strategy. [[arc:consult]]"
_NOTE = "the 3D7 one"
_DRAFTS = pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (None, IntentClassification.NEW_STRATEGY),
        (framed(None), IntentClassification.EXTEND_STRATEGY),
    ],
    ids=["nothing_framed", "a_framed_draft"],
)


@_DRAFTS
def test_a_build_request_extends_only_a_framed_draft(
    spec: OperationalSpec | None, expected: IntentClassification
) -> None:
    state = pipeline_state(
        user_prompt=_BUILD, domain=StrategyDomainState(operational_spec=spec)
    )

    assert scripted_intent(state, _BUILD).classification == expected


@_DRAFTS
def test_a_note_on_a_resumed_consult_extends_only_a_framed_draft(
    spec: OperationalSpec | None, expected: IntentClassification
) -> None:
    state = pipeline_state(
        domain=StrategyDomainState(
            operational_spec=spec, exchanges=[Exchange(said=_CONSULT)]
        )
    )
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="c1", tool_name="consult_user"
    )
    state.user_question_answers = {
        "c1": [UserQuestionAnswer(question_id="q1", prompt="Which?", note=_NOTE)]
    }

    assert scripted_intent(state, _NOTE).classification == expected
