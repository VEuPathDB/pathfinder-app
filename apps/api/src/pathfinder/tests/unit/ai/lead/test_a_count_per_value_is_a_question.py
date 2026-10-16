"""A count per value of a column is a question the column tally answers, never a build."""

from __future__ import annotations

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    user_intent,
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_classifier_names_a_count_per_value_a_question() -> None:
    doc = _flat(classify_user_intent.__doc__ or "")

    assert "unless it compares counts, counts records per value of a column" in doc
    assert (
        "is a ``follow_up_question`` answered by ``count_by_column``, also on a "
        "conversation with no strategy" in doc
    )


def test_the_build_rule_leaves_a_count_per_value_to_the_tally() -> None:
    rules = _flat(LEAD_INSTRUCTIONS)

    assert (
        "A count per value of a column is not one: it is ``count_by_column``" in rules
    )


def test_a_question_turn_with_no_strategy_reaches_the_tally_and_no_build() -> None:
    state = pipeline_state(
        "vectorbase",
        user_prompt=(
            "Which genome assembly for the Anopheles gambiae species complex has "
            "the most RNA-Seq data?"
        ),
    )
    state.turn_markers.intent_classified = True
    deps = lead_deps(state, intent=user_intent(IntentClassification.FOLLOW_UP_QUESTION))

    offered = tools_the_turn_offers(deps, ["count_by_column", "frame_problem"])

    assert offered == frozenset({"count_by_column"})
