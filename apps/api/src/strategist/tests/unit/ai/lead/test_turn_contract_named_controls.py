"""The contract rules over a turn whose message names the researcher's controls."""

from __future__ import annotations

from uuid import uuid4

from strategist.ai.graph.turn_records import CreatedControlSet
from strategist.ai.lead.intent import (
    IntentClassification,
    NamedControls,
    UserIntent,
)
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_contract import reconcile
from strategist.ai.lead.turn_record import turn_record
from strategist.domain.strategy.questions import AskedQuestion
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead._turn_contract_cases import reply
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

SAVED = "I saved your two genes as a control set."
ASKS_FOR_NEGATIVES = "Which genes should I use as negative controls?"
CONTROLS = NamedControls(positive_ids=["PF3D7_0709000", "PF3D7_1133400"])


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
