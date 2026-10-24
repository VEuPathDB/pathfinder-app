"""A count per value of a column is counted on the step that holds the records,
a catalog search's whole result is counted with no step, and any other count is
a build."""

from __future__ import annotations

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import UNCLASSIFIED_TOOLS, tools_the_turn_offers
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    user_intent,
)

_RULE_HEAD = (
    "A count per value of a column is counted on the step that holds the records."
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _count_rule() -> str:
    rules = _flat(LEAD_INSTRUCTIONS)
    start = rules.index(_RULE_HEAD)
    return rules[start : rules.index("- **", start)]


def test_the_lead_counts_per_value_on_the_step_that_holds_the_records() -> None:
    assert _count_rule() == (
        f"{_RULE_HEAD}** ``step_columns`` names the step's columns, then "
        "``count_step_by_column`` counts one marked countable. When no step holds "
        "those records, the question is a build (``new_strategy`` with no strategy, "
        "``extend_strategy`` on one), and the count follows the build, through a "
        "transform when the records are a result's members. ``count_by_column`` "
        "counts only one catalog search's whole result, unchanged, with no step, and "
        "only by a search name the catalog lists. Name the value with the most and "
        "its count with ``[tally:<id>.<value>]``, the total with ``[tally:<id>]`` and "
        "the number of values with ``[tally:<id>:values]``; never a value's count for "
        "another number. "
    )


def test_the_count_rule_names_no_question() -> None:
    assert '"' not in _count_rule()


def test_no_other_rule_sends_a_count_per_value_to_the_catalog_tally() -> None:
    rules = _flat(LEAD_INSTRUCTIONS)

    assert rules.count("``count_by_column``") == 1


def test_the_classifier_names_where_a_count_per_value_is_answered() -> None:
    doc = _flat(classify_user_intent.__doc__ or "")

    assert (
        "is a ``follow_up_question`` when a step of the strategy holds those records, "
        "answered by ``count_step_by_column``, or when the records are one catalog "
        "search's whole result, unchanged, answered by ``count_by_column``" in doc
    )
    assert (
        "When no step holds those records and no one search's whole result is them, "
        "it asks for a build" in doc
    )


def test_an_unclassified_turn_reaches_the_step_tally() -> None:
    assert {"step_columns", "count_step_by_column", "count_by_column"} <= (
        UNCLASSIFIED_TOOLS
    )
    state = pipeline_state("orthomcl", user_prompt="Count these proteins by genome.")
    deps = lead_deps(state)

    offered = tools_the_turn_offers(
        deps, ["step_columns", "count_step_by_column", "frame_problem"]
    )

    assert offered == frozenset({"step_columns", "count_step_by_column"})


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
