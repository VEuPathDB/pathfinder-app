"""A count per value of a column is counted on the step that holds the records,
a catalog search's whole result is counted with no step, and any other count is
a build."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.intent import (
    ClassifiedIntent,
    IntentClassification,
    UserIntent,
)
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
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
        "A count per value that needs a build first, because no step holds those "
        "records and no one search's whole result is them, is a build: "
        "``new_strategy`` with no strategy, and on a conversation with one "
        "``extend_strategy`` with ``asks_a_change`` set, so the request is never "
        "held as a question." in doc
    )
    assert "counts records per value of a column, or" not in doc


_COUNT = "How many records of the result does each value of that column hold?"


def _count_intent(classification: IntentClassification, *, change: bool) -> UserIntent:
    return UserIntent(
        classification=classification,
        inferred_goal="The result's records counted by each value of a column.",
        asks=[_COUNT],
        asks_a_change=change,
    )


async def test_a_count_that_needs_a_build_is_a_build_with_no_strategy() -> None:
    state = pipeline_state("plasmodb", user_prompt=_COUNT, user_message_id=uuid4())
    deps = lead_deps(state)
    ctx = run_context_for(deps, tool_call_id="call_classify")

    returned = await classify_user_intent(
        ctx, _count_intent(IntentClassification.NEW_STRATEGY, change=False)
    )

    held = ClassifiedIntent.model_validate(returned.return_value)
    assert held.intent.classification is IntentClassification.NEW_STRATEGY
    assert tools_the_turn_offers(deps, ["frame_problem", "build_strategy"]) == {
        "frame_problem",
        "build_strategy",
    }
