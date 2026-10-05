"""A turn that stops after its change landed says whether a check of that
change ran to its end."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph._lead_stops import strategy_change
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead._budget_stop_turn import (
    built_outcome,
    built_session,
    objection,
)
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state


def _built(*, dispatched: bool, stopped: bool = False) -> PipelineState:
    """A turn that built one step, with a verdict on the strategy it built."""
    state = pipeline_state(user_prompt="find the 24 h responders")
    state.user_message_id = uuid4()
    state.record_build(built_outcome())
    state.domain.answered_graph = live_tree(built_session().get_graph(None))
    state.domain.record_verdict(
        objection(), revision=strategy_revision(state.domain.answered_graph)
    )
    state.turn_markers.verification_dispatched = dispatched
    state.turn_markers.verification_stopped = stopped
    return state


def test_a_change_is_checked_only_by_a_check_that_ran_to_its_end() -> None:
    assert [
        strategy_change(pipeline_state(user_prompt="what is a kinase?")),
        strategy_change(_built(dispatched=False)),
        strategy_change(_built(dispatched=True, stopped=True)),
        strategy_change(_built(dispatched=True)),
    ] == ["unchanged", "unchecked", "unchecked", "checked"]


def test_a_check_of_an_earlier_revision_leaves_the_change_unchecked() -> None:
    state = _built(dispatched=True)
    state.domain.record_verdict(objection(), revision="the revision before the edit")

    assert strategy_change(state) == "unchecked"
