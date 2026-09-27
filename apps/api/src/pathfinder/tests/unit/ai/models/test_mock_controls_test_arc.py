"""The controls-test arc saves the controls a message pastes before the check."""

from __future__ import annotations

from pathfinder.tests.unit.ai.models._mock_turns import (
    args_of,
    built_thread,
    names,
    play,
)


def test_the_controls_test_saves_the_pasted_controls_before_the_check() -> None:
    text = (
        "Test this strategy against my controls. [[arc:controls-test]]\n"
        "Positive controls: AGAP000046 AGAP000128\n"
        "Negative controls: AGAP000427"
    )

    calls = play("lead", "vectorbase", text, scene=built_thread())

    assert names(calls) == [
        "classify_user_intent",
        "build_control_set",
        "verify_strategy",
        "get_live_strategy_state",
        "final_result",
    ]
    assert args_of(calls, "build_control_set") == [
        {
            "name": "Controls from this message",
            "positive_ids": ["AGAP000046", "AGAP000128"],
            "negative_ids": ["AGAP000427"],
        }
    ]
