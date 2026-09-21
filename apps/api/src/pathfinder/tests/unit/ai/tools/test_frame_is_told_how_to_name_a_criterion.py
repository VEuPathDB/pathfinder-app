"""FRAME learns the id rule for a new criterion before a call is refused for it."""

from __future__ import annotations

from pathfinder.ai.tools.standalone.frame_spec import set_criterion


def test_the_tool_description_states_the_id_a_new_criterion_may_not_take() -> None:
    description = set_criterion.__doc__ or ""

    assert "criterion_id" in description
    assert "step_" in description
