"""The contract rules over a turn whose classification was refused, and over
a turn whose message names the researcher's controls."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import PendingApproval

from pathfinder.ai.graph.turn_records import CreatedControlSet
from pathfinder.ai.lead.intent import (
    IntentClassification,
    NamedControls,
    RefusedClassification,
    UserIntent,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.questions import AskedQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

REFUSAL = (
    'The combination "signal peptide OR transmembrane domains" joins its '
    "requirements with OR, but the researcher's message does not."
)
GAVE_UP = "I could not build the search, so the strategy is unchanged."
SAVED = "I saved your two genes as a control set."
ASKS_FOR_NEGATIVES = "Which genes should I use as negative controls?"
CONTROLS = NamedControls(positive_ids=["PF3D7_0709000", "PF3D7_1133400"])


def _refused_turn() -> LeadDeps:
    """A turn whose one classification the gate refused."""
    deps = lead_deps(pipeline_state(user_prompt="Find genes.", user_message_id=uuid4()))
    deps.refused_classification = RefusedClassification(
        intent=UserIntent(
            classification=IntentClassification.NEW_STRATEGY,
            inferred_goal="genes",
        ),
        sentence=REFUSAL,
    )
    return deps


def _naming_controls() -> LeadDeps:
    """A classified turn whose message names two positive controls."""
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="Save the positive controls.",
        named_controls=CONTROLS,
    )
    deps = lead_deps(
        pipeline_state(user_prompt="Use these.", user_message_id=uuid4()),
        intent=intent,
    )
    deps.state.turn_markers.intent_classified = True
    return deps


def _mismatches(
    deps: LeadDeps,
    prose: str,
    questions: list[AskedQuestion] | None = None,
    *,
    card: bool = False,
) -> list[tuple[str, str]]:
    report = reply(prose, questions=questions)
    record = turn_record(run_context_for(deps))
    if card:
        record = record.model_copy(update={"ends_on_a_card": True})
    return [(m.kind, m.sentence) for m in reconcile(report, record)]


def test_a_reply_over_a_refused_classification_is_refused() -> None:
    assert _mismatches(_refused_turn(), GAVE_UP) == [
        (
            "unclassified_turn",
            (
                "This turn's message holds no accepted classification: "
                f"classify_user_intent refused it with this sentence. {REFUSAL} "
                "Call classify_user_intent again with what the sentence names, "
                "or ask the researcher the question it states through "
                "consult_user."
            ),
        )
    ]


def test_an_accepted_classification_after_a_refusal_passes() -> None:
    deps = _refused_turn()
    deps.refused_classification = None
    deps.intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY, inferred_goal="genes"
    )
    deps.state.turn_markers.intent_classified = True

    assert _mismatches(deps, GAVE_UP) == []


def test_a_card_answer_is_exempt() -> None:
    deps = _refused_turn()
    deps.state.turn_markers.consulted = True

    assert _mismatches(deps, GAVE_UP) == []


def test_a_typed_acceptance_is_exempt() -> None:
    deps = _refused_turn()
    deps.state.turn_markers.accepted_proposal = True

    assert _mismatches(deps, GAVE_UP) == []


def test_a_reply_that_ends_on_a_card_is_exempt() -> None:
    assert _mismatches(_refused_turn(), GAVE_UP, card=True) == []


def test_a_turn_that_re_enters_a_parked_call_is_exempt() -> None:
    deps = _refused_turn()
    deps.state.pending_approval = PendingApproval(
        phase="lead",
        tool_call_id="call_card",
        tool_name="consult_user",
        tool_args={},
        prior_messages_json="[]",
        user_message_id=deps.state.user_message_id,
    )

    assert _mismatches(deps, GAVE_UP) == []


def test_named_controls_saved_as_a_control_set_pass() -> None:
    deps = _naming_controls()
    deps.state.turn_markers.record_control_set(
        CreatedControlSet(id="cs-1", name="Controls from controls.csv")
    )

    assert _mismatches(deps, SAVED) == []


def test_named_controls_with_a_recorded_question_pass() -> None:
    deps = _naming_controls()
    asked = [AskedQuestion(question=ASKS_FOR_NEGATIVES)]

    assert _mismatches(deps, ASKS_FOR_NEGATIVES, questions=asked) == []


def test_named_controls_on_a_reply_that_ends_on_a_card_pass() -> None:
    assert _mismatches(_naming_controls(), ASKS_FOR_NEGATIVES, card=True) == []


def test_named_controls_neither_saved_nor_asked_about_are_refused() -> None:
    assert _mismatches(_naming_controls(), "Stored them for later.") == [
        (
            "unsaved_controls",
            (
                "The message names 2 positive and 0 negative controls, and this "
                "turn saved no control set. Save them with build_control_set; "
                "with positives only, save them and ask for the negatives."
            ),
        )
    ]


def test_empty_control_lists_name_no_controls() -> None:
    """A classification with both control lists empty names no control to save."""
    deps = _naming_controls()
    assert deps.intent is not None
    deps.intent = deps.intent.model_copy(
        update={"named_controls": NamedControls(positive_ids=[], negative_ids=[])}
    )

    assert _mismatches(deps, "The two counts differ by the Union step.") == []
