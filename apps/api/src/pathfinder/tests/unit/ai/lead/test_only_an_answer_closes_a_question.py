"""A message closes the thread's open questions only when it can answer one."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.graph.turn_records import AnsweredQuestions
from pathfinder.ai.lead.frame_dispatch import frame_work_order
from pathfinder.ai.lead.intent import ANSWERING_INTENTS, IntentClassification
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    OpenQuestion,
    standing_recommendations,
)
from pathfinder.tests.unit.ai.lead._answered_draft import (
    QUESTION,
    classify,
    draft_deps,
    framed,
)
from pathfinder.tests.unit.ai.lead.conftest import session_with_one_step

_ASIDE = "What does a GPI anchor mean here?"
_ANSWER = "ok, use signal peptide evidence"
_RECOMMENDED = standing_recommendations([QUESTION], [])


def _asked() -> StrategyDomainState:
    return StrategyDomainState(
        operational_spec=framed(None),
        open_questions=[QUESTION],
        recommendations=list(_RECOMMENDED),
    )


def test_the_answering_intents_are_the_answers_and_the_changes() -> None:
    assert frozenset(IntentClassification) - ANSWERING_INTENTS == {
        IntentClassification.NEW_STRATEGY,
        IntentClassification.FOLLOW_UP_QUESTION,
        IntentClassification.OFF_TOPIC,
        IntentClassification.CONTEXT_STATEMENT,
        IntentClassification.MEMORY_REQUEST,
    }


@pytest.mark.parametrize(
    "kind",
    sorted(
        frozenset(IntentClassification)
        - ANSWERING_INTENTS
        - {IntentClassification.NEW_STRATEGY}
    ),
)
def test_a_message_that_answers_nothing_leaves_the_question_open(
    kind: IntentClassification,
) -> None:
    deps = draft_deps(_ASIDE, domain=_asked())

    classify(deps, kind)

    domain = deps.state.domain
    assert domain.open_questions == [QUESTION]
    assert [c.requested_value for c in domain.recommendations] == ["signal peptide"]
    assert deps.state.turn_markers.answered is None


@pytest.mark.parametrize(
    "kind",
    [
        IntentClassification.CLARIFICATION_RESPONSE,
        IntentClassification.SLOT_ANSWER,
        IntentClassification.APPROVAL,
        IntentClassification.DENIAL,
        IntentClassification.EDIT_STRATEGY,
        IntentClassification.EXTEND_STRATEGY,
    ],
)
def test_a_message_that_can_answer_closes_the_question(
    kind: IntentClassification,
) -> None:
    deps = draft_deps(_ANSWER, domain=_asked())

    classify(deps, kind)

    assert deps.state.domain.open_questions == []
    assert deps.state.turn_markers.answered == AnsweredQuestions(
        questions=[QUESTION], answer=_ANSWER
    )


@pytest.mark.parametrize("built", [False, True], ids=["no_step", "a_built_step"])
def test_a_new_request_drops_the_questions_and_answers_none(built: bool) -> None:
    """The questions were about the request the message sets aside."""
    session = session_with_one_step() if built else None
    deps = draft_deps(_ANSWER, domain=_asked(), strategy_session=session)

    classify(deps, IntentClassification.NEW_STRATEGY)

    assert deps.state.domain.open_questions == []
    assert deps.state.turn_markers.answered is None


def test_the_answer_after_an_aside_continues_the_asked_draft() -> None:
    deps = draft_deps(_ASIDE, domain=_asked())
    classify(deps, IntentClassification.FOLLOW_UP_QUESTION)
    deps.state.user_prompt = _ANSWER
    deps.state.user_message_id = uuid4()

    classify(deps, IntentClassification.CLARIFICATION_RESPONSE)
    order = frame_work_order("bind the evidence", deps)

    assert order.splitlines()[0] == (
        "FRAME work order: the previous pass ended with a question the "
        "researcher has now answered. Continue it; this is not a fresh frame."
    )
    assert f"Question asked: {QUESTION.question}\nAnswer: {_ANSWER}\n" in order


_ASKED_THIS_TURN = OpenQuestion(
    question="Which life stage should the expression criterion read?",
    dimension=ConstraintKind.COMPARATOR,
)


def test_a_reclassification_to_an_answer_closes_the_question_open_at_arrival() -> None:
    """A corrected classifier still answers what was open when the message came."""
    deps = draft_deps(_ANSWER, domain=_asked())
    classify(deps, IntentClassification.FOLLOW_UP_QUESTION)

    classify(deps, IntentClassification.CLARIFICATION_RESPONSE, call_id="t_classify_2")

    assert deps.state.domain.open_questions == []
    assert deps.state.turn_markers.answered == AnsweredQuestions(
        questions=[QUESTION], answer=_ANSWER
    )


def test_a_reclassification_closes_only_the_question_open_at_arrival() -> None:
    """A question this turn asked waits on the next message's answer."""
    deps = draft_deps(_ANSWER, domain=_asked())
    classify(deps, IntentClassification.FOLLOW_UP_QUESTION)
    deps.state.domain.record_questions([_ASKED_THIS_TURN])

    classify(deps, IntentClassification.CLARIFICATION_RESPONSE, call_id="t_classify_2")

    assert deps.state.domain.open_questions == [_ASKED_THIS_TURN]
    assert deps.state.turn_markers.answered == AnsweredQuestions(
        questions=[QUESTION], answer=_ANSWER
    )


def test_the_arrival_record_is_a_copy_of_the_questions_open_then() -> None:
    deps = draft_deps(_ANSWER, domain=_asked())

    markers = deps.state.turn_markers
    deps.state.domain.record_questions([_ASKED_THIS_TURN])

    assert markers.questions_at_arrival == [QUESTION.question]
