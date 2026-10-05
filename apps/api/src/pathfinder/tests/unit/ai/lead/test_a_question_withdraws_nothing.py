"""A question changes no requirement, so a question classification that
withdraws one is refused: the message asks for the change, or it only asks
what the change would do and withdraws nothing."""

from __future__ import annotations

from pathfinder.ai.lead.classification_gate import (
    SiteReading,
    classification_refusal,
)
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

# A hostdb message that changes a value and asks what the change does.
_CHANGE = "Change the chromosome to 19. How does the count change?"
_CHROMOSOME_17 = Constraint(
    kind=ConstraintKind.OTHER, label="chromosome", requested_value="chromosome 17"
)


def _intent(
    classification: IntentClassification, withdrawn: list[Constraint]
) -> UserIntent:
    return UserIntent(
        classification=classification,
        inferred_goal="Compare the chromosome 17 count with chromosome 19.",
        asks=["How does the count change?"],
        withdrawn=withdrawn,
    )


def test_a_question_that_withdraws_what_its_message_changes_is_an_edit() -> None:
    state = pipeline_state("hostdb", user_prompt=_CHANGE)

    refusal = classification_refusal(
        state,
        _intent(IntentClassification.FOLLOW_UP_QUESTION, [_CHROMOSOME_17]),
        SiteReading(),
    )

    assert refusal == (
        "The classification withdraws 'chromosome 17', and a question withdraws "
        "nothing. The message states the change outside its questions, so it asks "
        "for it: classify it as the request it is (edit_strategy for a change to "
        "the strategy), state each value it asks for in explicit_constraints and "
        "keep its question in asks."
    )


def test_a_question_that_only_asks_what_a_change_would_do_withdraws_nothing() -> None:
    what_if = "What would the count be on chromosome 19?"
    state = pipeline_state("hostdb", user_prompt=what_if)
    intent = _intent(IntentClassification.FOLLOW_UP_QUESTION, [_CHROMOSOME_17])

    refusal = classification_refusal(
        state, intent.model_copy(update={"asks": [what_if]}), SiteReading()
    )

    assert refusal == (
        "The classification withdraws 'chromosome 17', and a question withdraws "
        "nothing. The message only asks what a change would do, so withdraw nothing."
    )


def test_a_question_that_withdraws_nothing_and_an_edit_that_withdraws_pass() -> None:
    state = pipeline_state("hostdb", user_prompt=_CHANGE)

    assert [
        classification_refusal(state, intent, SiteReading())
        for intent in (
            _intent(IntentClassification.FOLLOW_UP_QUESTION, []),
            _intent(IntentClassification.EDIT_STRATEGY, [_CHROMOSOME_17]),
        )
    ] == [None, None]
