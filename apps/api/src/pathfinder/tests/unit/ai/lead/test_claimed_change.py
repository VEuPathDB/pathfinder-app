"""The reply's account of a strategy change, against what the turn wrote."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic_ai import DeferredToolRequests
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.state import TurnMarkers
from pathfinder.ai.lead.lead_agent import LeadResponse, refuse_a_misreported_change
from pathfinder.ai.lead.lead_tools import clear_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import conversation
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_CLAIMS_A_CHANGE = "I removed that unfiltered essentiality criterion."
_REPORTS_THE_STRATEGY = "The essentiality step filters nothing, so I left it."


def _reading_deps() -> LeadDeps:
    """A turn that read the strategy and wrote nothing."""
    state = pipeline_state(user_prompt="How does that step define essential?")
    state.user_message_id = uuid4()
    state.turn_markers.intent_classified = True
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1", "s2", "s3"],
        root_count=1,
    )
    return lead_deps(state)


def _step_ids(deps: LeadDeps) -> list[str]:
    graph = deps.runtime.strategy_session.get_graph(None)
    return [] if graph is None else sorted(graph.steps)


def _clearing_deps() -> LeadDeps:
    """A turn on a thread that holds one step."""
    state = pipeline_state(user_prompt="Scrap it and start over.")
    state.user_message_id = uuid4()
    return lead_deps(state, strategy_session=session_with_one_step())


def _building_deps() -> LeadDeps:
    """A turn that pushed a build."""
    state = pipeline_state(user_prompt="Add an essentiality filter.")
    state.user_message_id = uuid4()
    state.record_build(BuildOutcome(pushed_step_ids=["s1"], root_count=132))
    return lead_deps(state)


def test_a_turn_that_wrote_nothing_changed_no_strategy() -> None:
    assert TurnMarkers().changed_strategy is False


def test_a_built_turn_changed_the_strategy() -> None:
    assert TurnMarkers(built=True).changed_strategy is True


def test_an_edited_turn_changed_the_strategy() -> None:
    assert TurnMarkers(edited=True).changed_strategy is True


def test_a_claimed_change_the_turn_never_made_is_refused() -> None:
    deps = _reading_deps()

    with pytest.raises(ModelRetry) as raised:
        refuse_a_misreported_change(
            run_context_for(deps),
            LeadResponse(prose=_CLAIMS_A_CHANGE, strategy_changed=True),
        )

    message = str(raised.value)
    assert "no build, edit, delete, clear or export" in message
    assert "3 step(s)" in message
    assert "root count 1" in message


def test_the_claimed_change_refusal_is_asked_once_per_turn() -> None:
    deps = _reading_deps()
    output = LeadResponse(prose=_CLAIMS_A_CHANGE, strategy_changed=True)

    with pytest.raises(ModelRetry):
        refuse_a_misreported_change(run_context_for(deps), output)

    assert refuse_a_misreported_change(run_context_for(deps), output) is output


def test_a_change_the_reply_leaves_out_is_refused() -> None:
    deps = _building_deps()

    with pytest.raises(ModelRetry) as raised:
        refuse_a_misreported_change(
            run_context_for(deps),
            LeadResponse(prose=_REPORTS_THE_STRATEGY, strategy_changed=False),
        )

    assert "strategy_changed to true" in str(raised.value)


def test_a_reported_change_that_matches_the_build_stands() -> None:
    output = LeadResponse(prose="I added the step.", strategy_changed=True)

    assert (
        refuse_a_misreported_change(run_context_for(_building_deps()), output) is output
    )


def test_a_reply_that_reports_no_change_on_a_read_turn_stands() -> None:
    output = LeadResponse(prose=_REPORTS_THE_STRATEGY, strategy_changed=False)

    assert (
        refuse_a_misreported_change(run_context_for(_reading_deps()), output) is output
    )


def test_a_deferred_request_is_not_prose() -> None:
    output = DeferredToolRequests()

    assert (
        refuse_a_misreported_change(run_context_for(_reading_deps()), output) is output
    )


@pytest.fixture
def no_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """The clear runs against the in-memory graph and writes no row."""

    async def _persisted(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        conversation, "persist_strategy_ast_to_conversation", _persisted
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_persistence")
async def test_a_cleared_strategy_marks_the_turn() -> None:
    deps = _clearing_deps()

    await clear_strategy(run_context_for(deps), confirm=True)

    assert _step_ids(deps) == []
    assert deps.state.turn_markers.edited is True
    assert deps.state.turn_markers.changed_strategy is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_persistence")
async def test_an_unconfirmed_clear_marks_nothing() -> None:
    deps = _clearing_deps()

    with pytest.raises(ModelRetry):
        await clear_strategy(run_context_for(deps), confirm=False)

    assert _step_ids(deps) == ["step_a"]
    assert deps.state.turn_markers.edited is False
    assert deps.state.turn_markers.changed_strategy is False
