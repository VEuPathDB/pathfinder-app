"""The pins the Lead's instructions render from the turn state."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.lead_pins import pinned_turn_briefing
from pathfinder.ai.lead.turn_briefing import compose_turn_briefing
from pathfinder.services.conversations.thread_activity import ThreadActivity
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state


def _briefed_ctx(briefing: str) -> Any:
    ctx = MagicMock()
    ctx.deps.state = pipeline_state(
        domain=StrategyDomainState(turn_briefing=briefing),
    )
    return ctx


def test_the_pin_renders_the_briefing_the_pre_turn_hook_wrote() -> None:
    assert pinned_turn_briefing(_briefed_ctx("## Since your last turn\n- x")) == (
        "## Since your last turn\n- x"
    )


def test_a_quiet_turn_pins_nothing() -> None:
    briefing = compose_turn_briefing(ThreadActivity(), requirements=[])

    assert briefing.render() == ""
    assert pinned_turn_briefing(_briefed_ctx(briefing.render())) is None
