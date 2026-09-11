"""The tools the Lead carries itself: classification and clearing."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS, UNCLASSIFIED_TOOLS
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.lead_tools import classify_user_intent, clear_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.toolsets import execution
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.sub_agents import toolset_tool_names
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    lead_run_context,
    pipeline_state,
    session_with_one_step,
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _cleared_session() -> StrategySession:
    session = session_with_one_step()
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_a": 100},
        wdk_strategy_id=555,
    )
    return session


def _ctx() -> RunContext[LeadDeps]:
    state = pipeline_state(user_prompt="scrap this and start again")
    return lead_run_context(
        lead_deps(state, strategy_session=_cleared_session()),
        tool_call_id="call_clear",
    )


@pytest.fixture
def _no_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "pathfinder.ai.tools.standalone.conversation."
        "persist_strategy_ast_to_conversation",
        _noop,
    )


def test_research_is_reachable_before_the_turn_is_classified() -> None:
    """The two served reads answer a question that has not been classified."""
    assert "research_web_search" in UNCLASSIFIED_TOOLS
    assert "research_literature_search" in UNCLASSIFIED_TOOLS
    assert not UNCLASSIFIED_TOOLS & BUILDING_TOOLS


def test_the_classifier_calls_an_imperative_a_building_intent() -> None:
    guidance = _flat(classify_user_intent.__doc__ or "")

    assert "An imperative asks for a build" in guidance
    assert "rerun" in guidance
    assert "yes, do it" in guidance
    assert "None of them is a ``follow_up_question``" in guidance


def test_the_classifier_keeps_a_retry_on_the_request_s_own_intent() -> None:
    guidance = _flat(classify_user_intent.__doc__ or "")

    assert "A retry after a failed task is the same request again" in guidance


def test_the_classifier_guidance_is_ascii_only() -> None:
    assert (classify_user_intent.__doc__ or "").isascii()


def test_the_classifier_is_told_to_capture_a_stated_share() -> None:
    doc = classify_user_intent.__doc__ or ""
    assert "percentile" in doc
    assert "top 10%" in doc


def test_the_lead_registers_the_clear_tool_behind_an_approval() -> None:
    tools = build_lead_agent()._function_toolset.tools

    assert "clear_strategy" in tools
    assert tools["clear_strategy"].requires_approval is True


def test_the_recovery_sub_agent_cannot_clear_the_strategy() -> None:
    """One destructive door, and the Lead holds it."""
    assert "clear_strategy" not in toolset_tool_names(execution.build_toolset())


def test_the_clear_docstring_does_not_claim_the_provenance_is_lost() -> None:
    """Clearing appends a revision, so a revert restores what it cleared."""
    doc = _flat(clear_strategy.__doc__ or "")

    assert "provenance" not in doc
    assert "destructive" in doc
    assert "revision" in doc


@pytest.mark.usefixtures("_no_persist")
async def test_clearing_empties_the_strategy_the_lead_can_see() -> None:
    ctx = _ctx()

    returned = await clear_strategy(ctx, confirm=True)

    graph = ctx.deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    assert graph.steps == {}
    assert ctx.deps.runtime.strategy_session.sync_state.wdk_strategy_id is None
    assert returned.return_value.graph_id == "g1"


@pytest.mark.usefixtures("_no_persist")
async def test_clearing_without_confirmation_is_a_retry() -> None:
    ctx = _ctx()

    with pytest.raises(ModelRetry):
        await clear_strategy(ctx, confirm=False)

    graph = ctx.deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    assert sorted(graph.steps) == ["step_a"]
