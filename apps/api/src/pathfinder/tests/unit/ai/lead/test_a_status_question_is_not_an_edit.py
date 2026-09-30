"""A message that asks whether a change went through, or what the count is
now, is a question about the strategy: a request classification of it is
refused, and a question classification reaches no framing tool."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.lead.classification_gate import SiteReading, classification_refusal
from pathfinder.ai.lead.intent import (
    BUILDING_INTENTS,
    IntentClassification,
    UserIntent,
)
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_STATUS = (
    "I got an error message saying the content was flagged for biological risk "
    "and to send the message again. Did my change to ME49-only go through? What "
    "is the count now?"
)
_ASKS = ["Did my change to ME49-only go through?", "What is the count now?"]
# The constraints the classifier restated from the conversation on that turn.
_RESTATED = [
    Constraint(
        kind=ConstraintKind.ORGANISM,
        label="source organism",
        requested_value="Cryptosporidium parvum Iowa II",
    ),
    Constraint(
        kind=ConstraintKind.COMBINATION,
        label="orthology requirements",
        requested_value="ortholog in Toxoplasma gondii ME49 AND no ortholog in Homo sapiens",
    ),
    Constraint(
        kind=ConstraintKind.OTHER,
        label="display naming",
        requested_value="use strain names, not codes",
    ),
]


def _refusal(
    message: str,
    classification: IntentClassification,
    *,
    asks: list[str],
    stated: list[Constraint],
) -> str | None:
    state = pipeline_state("cryptodb", user_prompt=message, user_message_id=uuid4())
    intent = UserIntent(
        classification=classification,
        inferred_goal="Confirm the ME49-only change and report the count.",
        asks=asks,
        explicit_constraints=stated,
    )
    return classification_refusal(state, intent, SiteReading())


_REFUSED = (
    "The message states no change outside its questions (Did my change to "
    "ME49-only go through?; What is the count now?). A question about what the "
    "strategy holds, whether a change went through or what the count is now, is "
    "a follow_up_question: the facts answer it and nothing is framed. If the "
    "message asks for a change, asks lists only the words that ask for an "
    "answer, and the change goes in explicit_constraints."
)


def test_the_status_question_is_refused_as_an_edit_and_as_an_extension() -> None:
    refusals = [
        _refusal(_STATUS, classification, asks=_ASKS, stated=_RESTATED)
        for classification in (
            IntentClassification.EDIT_STRATEGY,
            IntentClassification.EXTEND_STRATEGY,
        )
    ]

    assert refusals == [_REFUSED, _REFUSED]


def test_a_bare_status_question_is_refused_as_an_edit() -> None:
    refusal = _refusal(
        "Did my change go through? What is the count now?",
        IntentClassification.EDIT_STRATEGY,
        asks=["Did my change go through?", "What is the count now?"],
        stated=[],
    )

    assert refusal == _REFUSED.replace(" to ME49-only", "")


def test_the_status_question_is_accepted_as_a_question_that_frames_nothing() -> None:
    accepted = _refusal(
        _STATUS, IntentClassification.FOLLOW_UP_QUESTION, asks=_ASKS, stated=_RESTATED
    )

    assert (accepted, IntentClassification.FOLLOW_UP_QUESTION in BUILDING_INTENTS) == (
        None,
        False,
    )


def test_a_change_stated_beside_the_question_and_a_rerun_are_requests() -> None:
    change = _refusal(
        "Change it to ortholog in T. gondii ME49 only. What is the count now?",
        IntentClassification.EDIT_STRATEGY,
        asks=["What is the count now?"],
        stated=[
            Constraint(
                kind=ConstraintKind.OTHER,
                label="ortholog",
                requested_value="ortholog in T. gondii ME49",
            )
        ],
    )
    rerun = _refusal(
        "Rerun it and tell me the count.",
        IntentClassification.EXTEND_STRATEGY,
        asks=["tell me the count"],
        stated=[],
    )

    assert [change, rerun] == [None, None]
