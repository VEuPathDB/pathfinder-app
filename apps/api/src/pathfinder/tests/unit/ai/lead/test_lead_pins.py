"""The pins the Lead's instructions render from the turn state."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_pins import pinned_turn_briefing
from pathfinder.ai.lead.turn_briefing import compose_turn_briefing
from pathfinder.services.conversations.thread_activity import (
    FinishedTask,
    ThreadActivity,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state


def _briefed_ctx(briefing: str, intent: UserIntent | None = None) -> Any:
    ctx = MagicMock()
    ctx.deps.state = pipeline_state(
        domain=StrategyDomainState(turn_briefing=briefing),
    )
    ctx.deps.intent = intent
    ctx.deps.state.turn_markers.intent_classified = intent is not None
    return ctx


def _intent(classification: IntentClassification) -> UserIntent:
    return UserIntent(classification=classification, inferred_goal="what was asked")


def test_the_pin_renders_the_briefing_the_pre_turn_hook_wrote() -> None:
    assert pinned_turn_briefing(_briefed_ctx("## Since your last turn\n- x")) == (
        "## Since your last turn\n- x"
    )


def test_a_quiet_turn_pins_nothing() -> None:
    briefing = compose_turn_briefing(ThreadActivity(), requirements=[])

    assert briefing.render() == ""
    assert pinned_turn_briefing(_briefed_ctx(briefing.render())) is None


def test_an_off_topic_turn_pins_the_redirect_after_the_briefing() -> None:
    pinned = pinned_turn_briefing(
        _briefed_ctx(
            "## Since your last turn\n- x",
            _intent(IntentClassification.OFF_TOPIC),
        ),
    )

    assert pinned is not None
    assert pinned.startswith("## Since your last turn\n- x")
    assert "two sentences" in pinned
    assert "no code" in pinned


def test_an_off_topic_turn_still_reports_a_task_that_finished() -> None:
    """The catch-up is windowed on the last answer, so this turn is its
    only chance to name the task."""
    briefing = compose_turn_briefing(
        ThreadActivity(
            finished_tasks=[FinishedTask(tool_name="optimize_search_parameters")]
        ),
        requirements=[],
    )
    pinned = pinned_turn_briefing(
        _briefed_ctx(briefing.render(), _intent(IntentClassification.OFF_TOPIC)),
    )

    assert pinned is not None
    assert "optimize_search_parameters finished" in pinned
    assert "two sentences" in pinned


def test_a_quiet_off_topic_turn_pins_the_redirect_alone() -> None:
    pinned = pinned_turn_briefing(
        _briefed_ctx("", _intent(IntentClassification.OFF_TOPIC)),
    )

    assert pinned is not None
    assert pinned.startswith("## This turn is out of scope")


def test_a_question_about_the_data_still_pins_the_briefing() -> None:
    assert pinned_turn_briefing(
        _briefed_ctx(
            "## Since your last turn\n- x",
            _intent(IntentClassification.FOLLOW_UP_QUESTION),
        ),
    ) == ("## Since your last turn\n- x")
