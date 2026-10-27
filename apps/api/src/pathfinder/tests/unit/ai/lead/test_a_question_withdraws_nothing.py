"""A question changes no requirement, so a question classification that
withdraws one is refused."""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    "message", [_CHANGE, "What would the count be on chromosome 19?"]
)
def test_a_question_that_withdraws_a_requirement_is_refused(message: str) -> None:
    state = pipeline_state("hostdb", user_prompt=message)

    refusal = classification_refusal(
        state,
        _intent(IntentClassification.FOLLOW_UP_QUESTION, [_CHROMOSOME_17]),
        SiteReading(),
    )

    assert refusal is not None
    assert refusal.startswith(
        "The classification withdraws 'chromosome 17', and a question withdraws "
        "nothing."
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
