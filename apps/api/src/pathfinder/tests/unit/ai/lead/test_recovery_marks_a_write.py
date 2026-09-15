"""A recovery pass marks the turn only when it wrote to the strategy."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import RunContext, Tool
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import sub_agent_dispatch, sub_agent_tools
from pathfinder.ai.lead.deltas import RecoveryDelta
from pathfinder.ai.lead.sub_agent_dispatch import run_recovery
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import (
    call_then_final_model,
    final_result_model,
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_REASON = "fix the step that pushed nothing"
_RECOVERY_FINAL: dict[str, Any] = {
    "actionsTaken": ["re-read the step"],
    "followUpNeeded": False,
}
_ROOT_COUNT = 214
_INSTRUCTIONS = "Follow the script."


def _deps(session: StrategySession) -> LeadDeps:
    state = pipeline_state(user_prompt="Recover it.", user_message_id=uuid4())
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["step_a"],
        root_count=0,
    )
    return lead_deps(state, strategy_session=session)


def _sync_result() -> SyncResult:
    return SyncResult(
        wdk_strategy_id=901,
        wdk_url="https://plasmodb.org/plasmo/app/workspace/strategies/901",
        root_step_id=5001,
        counts={"step_a": _ROOT_COUNT},
        root_count=_ROOT_COUNT,
        zero_step_ids=[],
        step_count=1,
    )


@pytest.fixture
def quiet_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """The re-sync reads counts and puts no step on VEuPathDB."""

    async def _sync(**_kwargs: object) -> SyncResult:
        return _sync_result()

    monkeypatch.setattr(sub_agent_dispatch, "sync_strategy_for_site", _sync)


def _renaming_toolset() -> FunctionToolset[AgentDeps]:
    """One tool that changes the search the step runs."""

    async def rename_the_search(ctx: RunContext[AgentDeps], search_name: str) -> str:
        graph = ctx.deps.strategy_session.get_graph(None)
        assert graph is not None
        graph.steps["step_a"].search_name = search_name
        return f"step_a now runs {search_name}"

    return FunctionToolset[AgentDeps](tools=[Tool(rename_the_search)])


@pytest.fixture
def renaming_sub_agent(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: call_then_final_model(
            "rename_the_search",
            {"search_name": "GenesByTaxon"},
            _RECOVERY_FINAL,
        ),
    )
    with pinned_sub_agent(
        monkeypatch,
        "execution",
        toolsets=[_renaming_toolset()],
        instructions=_INSTRUCTIONS,
    ):
        yield


@pytest.fixture
def idle_sub_agent(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A recovery pass that answers and calls no tool."""
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: final_result_model(_RECOVERY_FINAL),
    )
    with pinned_sub_agent(
        monkeypatch,
        "execution",
        toolsets=[_renaming_toolset()],
        instructions=_INSTRUCTIONS,
    ):
        yield


async def _recover(deps: LeadDeps) -> RecoveryDelta | object:
    return await run_recovery(
        deps=deps,
        parent_tool_call_id="lead_call_recover",
        reason=_REASON,
    )


@pytest.mark.usefixtures("collector", "idle_sub_agent", "quiet_sync")
async def test_a_recovery_that_wrote_nothing_leaves_the_turn_unchanged() -> None:
    session = session_with_one_step()
    deps = _deps(session)

    result = await _recover(deps)

    assert isinstance(result, RecoveryDelta)
    assert deps.state.turn_markers.built is False
    assert deps.state.turn_markers.changed_strategy is False


@pytest.mark.usefixtures("collector", "idle_sub_agent", "quiet_sync")
async def test_a_recovery_that_wrote_nothing_still_takes_the_fresh_counts() -> None:
    """The re-sync read the strategy, so the ledger reports what it read."""
    deps = _deps(session_with_one_step())

    await _recover(deps)

    outcome = deps.state.domain.last_build_outcome
    assert outcome is not None
    assert outcome.root_count == _ROOT_COUNT
    assert outcome.wdk_strategy_id == 901


@pytest.mark.usefixtures("collector", "renaming_sub_agent", "quiet_sync")
async def test_a_recovery_that_changed_a_step_marks_the_turn() -> None:
    session = session_with_one_step()
    deps = _deps(session)

    result = await _recover(deps)

    assert isinstance(result, RecoveryDelta)
    graph = session.get_graph(None)
    assert graph is not None
    assert graph.steps["step_a"].search_name == "GenesByTaxon"
    assert deps.state.turn_markers.built is True
    assert deps.state.turn_markers.changed_strategy is True


@pytest.mark.usefixtures("collector", "idle_sub_agent")
async def test_a_recovery_whose_resync_pushed_a_step_marks_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plan is untouched, and the step it names now stands on VEuPathDB."""
    session = session_with_one_step()

    async def _sync(**kwargs: object) -> SyncResult:
        del kwargs
        ensure_sync_state(session).wdk_step_ids["step_a"] = 5001
        return _sync_result()

    monkeypatch.setattr(sub_agent_dispatch, "sync_strategy_for_site", _sync)
    deps = _deps(session)

    await _recover(deps)

    assert deps.state.turn_markers.changed_strategy is True
