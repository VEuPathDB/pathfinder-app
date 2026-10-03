"""A message that asks whether a change went through, or what the count is
now, is a question about the strategy: the gate records a request
classification of it as a follow-up question, which reaches no framing tool."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.lead.classification_gate import (
    SiteReading,
    classification_refusal,
    held_as_question,
)
from pathfinder.ai.lead.intent import (
    BUILDING_INTENTS,
    ClassifiedIntent,
    IntentClassification,
    NamedControls,
    UserIntent,
)
from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS, tools_the_turn_offers
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

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


def _intent(
    classification: IntentClassification,
    *,
    asks: list[str],
    stated: list[Constraint],
) -> UserIntent:
    return UserIntent(
        classification=classification,
        inferred_goal="Confirm the ME49-only change and report the count.",
        asks=asks,
        explicit_constraints=stated,
    )


def _question(
    message: str,
    classification: IntentClassification,
    *,
    asks: list[str],
    stated: list[Constraint],
) -> UserIntent | None:
    state = pipeline_state("cryptodb", user_prompt=message, user_message_id=uuid4())
    return held_as_question(state, _intent(classification, asks=asks, stated=stated))


RECORDED = (
    "Recorded as a follow_up_question: the message states no change outside "
    "its questions; the facts answer it and nothing is framed."
)


def test_the_status_question_is_held_as_a_question_from_an_edit_and_an_extension() -> (
    None
):
    held = [
        _question(_STATUS, classification, asks=_ASKS, stated=_RESTATED)
        for classification in (
            IntentClassification.EDIT_STRATEGY,
            IntentClassification.EXTEND_STRATEGY,
        )
    ]

    expected = _intent(
        IntentClassification.FOLLOW_UP_QUESTION, asks=_ASKS, stated=_RESTATED
    )
    assert held == [expected, expected]


def test_a_bare_status_question_is_held_as_a_question() -> None:
    asks = ["Did my change go through?", "What is the count now?"]
    held = _question(
        "Did my change go through? What is the count now?",
        IntentClassification.EDIT_STRATEGY,
        asks=asks,
        stated=[],
    )

    assert held == _intent(
        IntentClassification.FOLLOW_UP_QUESTION, asks=asks, stated=[]
    )


def test_the_status_question_is_accepted_as_a_question_that_frames_nothing() -> None:
    state = pipeline_state("cryptodb", user_prompt=_STATUS, user_message_id=uuid4())
    intent = _intent(
        IntentClassification.FOLLOW_UP_QUESTION, asks=_ASKS, stated=_RESTATED
    )

    assert (
        held_as_question(state, intent),
        classification_refusal(state, intent, SiteReading()),
        IntentClassification.FOLLOW_UP_QUESTION in BUILDING_INTENTS,
    ) == (None, None, False)


def test_a_change_stated_beside_the_question_and_a_rerun_are_requests() -> None:
    change = _question(
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
    rerun = _question(
        "Rerun it and tell me the count.",
        IntentClassification.EXTEND_STRATEGY,
        asks=["tell me the count"],
        stated=[],
    )

    assert [change, rerun] == [None, None]


_VESA1 = (
    "Great, 146 looks more like it. How many of those VESA1 genes sit on "
    "chromosome 1? Keep the full list too, I want both."
)
_VESA1_ASKS = [
    "Great, 146 looks more like it. How many of those VESA1 genes sit on chromosome 1?",
    "Keep the full list too, I want both.",
]


async def test_the_gate_records_a_question_classified_as_an_extension() -> None:
    deps = lead_deps(pipeline_state("piroplasmadb", user_prompt=_VESA1))
    intent = UserIntent(
        classification=IntentClassification.EXTEND_STRATEGY,
        inferred_goal="Count the VESA1 genes on chromosome 1 and keep the list.",
        asks=_VESA1_ASKS,
    )

    returned = await classify_user_intent(run_context_for(deps), intent)

    classified = ClassifiedIntent.model_validate(returned.return_value)
    question = intent.model_copy(
        update={"classification": IntentClassification.FOLLOW_UP_QUESTION}
    )
    assert (classified.intent, classified.corrections, deps.intent) == (
        question,
        [RECORDED],
        question,
    )
    assert deps.state.turn_markers.intent_classified is True


def test_an_edit_whose_value_stands_outside_its_asks_is_kept() -> None:
    message = "Raise the fold change to 4. What is the count now?"
    intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="Raise the fold change cut to 4.",
        asks=["What is the count now?"],
        explicit_constraints=[
            Constraint(
                kind=ConstraintKind.OTHER,
                label="fold change",
                requested_value="fold change 4",
            )
        ],
    )
    state = pipeline_state("plasmodb", user_prompt=message)

    assert (
        held_as_question(state, intent),
        classification_refusal(state, intent, SiteReading()),
    ) == (None, None)


def test_an_off_topic_message_that_names_a_site_gene_is_still_refused() -> None:
    state = pipeline_state("plasmodb", user_prompt="Write a poem about PF3D7_0709000.")
    intent = UserIntent(
        classification=IntentClassification.OFF_TOPIC, inferred_goal="A poem."
    )

    refusal = classification_refusal(
        state, intent, SiteReading(genes=frozenset({"pf3d7_0709000"}))
    )

    assert refusal == (
        "The message names PF3D7_0709000, genes of this site, so it is in "
        "scope. Classify it by what it asks of them."
    )


_POSITIVES = ["PF3D7_0100600", "PF3D7_0100800"]
_NEGATIVES = ["PF3D7_0111300", "PF3D7_0215800"]
_CONTROLS = (
    "Test this strategy against my controls.\n"
    f"Positive controls: {', '.join(_POSITIVES)}\n"
    f"Negative controls: {', '.join(_NEGATIVES)}"
)


@pytest.mark.usefixtures("recorded_site_organisms")
async def test_a_request_to_test_against_controls_is_a_building_turn() -> None:
    """An ask that names a check keeps the classification the model sent."""
    state = pipeline_state("plasmodb", user_prompt=_CONTROLS)
    deps = lead_deps(state, strategy_session=session_with_one_step("plasmodb"))
    intent = UserIntent(
        classification=IntentClassification.EXTEND_STRATEGY,
        inferred_goal="Test the signal peptide strategy against the controls.",
        asks=["Test this strategy against my controls"],
        explicit_constraints=[
            Constraint(
                kind=ConstraintKind.ORGANISM,
                label="organism",
                requested_value="Plasmodium falciparum 3D7",
            ),
            Constraint(
                kind=ConstraintKind.OTHER,
                label="protein feature",
                requested_value="predicted signal peptide",
            ),
        ],
        named_controls=NamedControls(positive_ids=_POSITIVES, negative_ids=_NEGATIVES),
    )

    returned = await classify_user_intent(run_context_for(deps), intent)

    classified = ClassifiedIntent.model_validate(returned.return_value)
    assert (classified.intent, classified.corrections) == (intent, [])
    assert "verify_strategy" in tools_the_turn_offers(deps, BUILDING_TOOLS)


@pytest.mark.parametrize(
    "ask", ["Check it", "verify the result", "validate it", "run the check again"]
)
def test_an_ask_that_names_a_check_is_not_held_as_a_question(ask: str) -> None:
    held = _question(
        f"{ask}.", IntentClassification.EXTEND_STRATEGY, asks=[ask], stated=[]
    )

    assert [held] == [None]
