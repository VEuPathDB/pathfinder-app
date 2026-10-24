"""A message the classifier marks as asking for a change to the strategy reaches
the framing tools, however it is worded."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.lead.classification_gate import (
    SiteReading,
    classification_refusal,
    held_as_question,
)
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_MESSAGE = "Could you show me what is inside those lanterns?"
_ASKS = [_MESSAGE]


def _intent(classification: IntentClassification, *, change: bool) -> UserIntent:
    return UserIntent(
        classification=classification,
        inferred_goal="The contents of the lanterns.",
        asks=_ASKS,
        asks_a_change=change,
    )


def test_a_question_that_asks_a_change_is_refused_as_a_question() -> None:
    state = pipeline_state("giardiadb", user_prompt=_MESSAGE, user_message_id=uuid4())

    refusal = classification_refusal(
        state,
        _intent(IntentClassification.FOLLOW_UP_QUESTION, change=True),
        SiteReading(),
    )

    assert refusal == (
        "The classification marks the message as asking for a change to the "
        "strategy, and a follow_up_question changes nothing. Classify it as the "
        "request it is: extend_strategy or edit_strategy over a strategy, "
        "new_strategy over none, and keep its question in asks."
    )


def test_a_question_that_asks_no_change_stands() -> None:
    state = pipeline_state("giardiadb", user_prompt=_MESSAGE, user_message_id=uuid4())

    refusal = classification_refusal(
        state,
        _intent(IntentClassification.FOLLOW_UP_QUESTION, change=False),
        SiteReading(),
    )

    assert [refusal] == [None]


def test_a_change_worded_as_a_question_is_not_held_as_one() -> None:
    state = pipeline_state("giardiadb", user_prompt=_MESSAGE, user_message_id=uuid4())
    marked = _intent(IntentClassification.EXTEND_STRATEGY, change=True)
    unmarked = _intent(IntentClassification.EXTEND_STRATEGY, change=False)

    assert (held_as_question(state, marked), held_as_question(state, unmarked)) == (
        None,
        unmarked.as_question(),
    )
