"""A count comparison is answered by the read-only comparison, never by a combine."""

from __future__ import annotations

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
    user_intent,
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_instructions_no_longer_build_one_step_per_organism() -> None:
    assert "one such step per organism" not in _flat(LEAD_INSTRUCTIONS)


def test_the_instructions_route_a_count_comparison_to_the_read_only_comparison() -> (
    None
):
    rules = _flat(LEAD_INSTRUCTIONS)

    assert (
        "A comparison of counts is a question, answered by ``compare_search_variants``"
        in rules
    )
    assert "never join the sides into the strategy with a combine" in rules


def test_the_classifier_names_a_count_comparison_a_question() -> None:
    doc = _flat(classify_user_intent.__doc__ or "")

    assert "compare the gene counts of three organisms" not in doc
    assert "A question that compares counts" in doc
    assert "is a ``follow_up_question`` answered by ``compare_search_variants``" in doc


def test_a_question_turn_over_a_built_strategy_reaches_the_comparison() -> None:
    """The DAL972 against TREU927 question: the comparison, and no edit."""
    state = pipeline_state(
        "tritrypdb",
        user_prompt=(
            "How does that count compare with the reference strain, Trypanosoma "
            "brucei brucei TREU927, using the same domains?"
        ),
    )
    state.turn_markers.intent_classified = True
    deps = lead_deps(
        state,
        intent=user_intent(IntentClassification.FOLLOW_UP_QUESTION),
        strategy_session=session_with_one_step("tritrypdb"),
    )

    offered = tools_the_turn_offers(
        deps, ["compare_search_variants", "edit_strategy", "frame_problem"]
    )

    assert offered == frozenset({"compare_search_variants"})


def test_the_instructions_say_what_the_lead_does_with_each_comparison() -> None:
    rules = _flat(LEAD_INSTRUCTIONS)

    assert "a variant whose scoring failed is reported as failed" in rules
    assert (
        "over a strategy that holds a step, the answers go to ``edit_strategy``"
        in rules
    )
