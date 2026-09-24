from __future__ import annotations

import asyncio
import dataclasses
from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.agents.state import AgentToolState, SearchOverview
from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database


def _build_context(*, cancel_event: asyncio.Event | None = None) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=cancel_event or asyncio.Event(),
    )


def _build_state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
    )


def _deps(state: PipelineState, ctx: Context) -> AgentDeps:
    return agent_deps_for(
        LeadDeps(state=state, intent=None, runtime=ctx, retrieved_memories=[])
    )


def test_agent_deps_is_pydantic_and_lists_live_fields() -> None:
    fields = set(AgentDeps.model_fields)
    assert fields == {
        "site_id",
        "user_id",
        "strategy_session",
        "tool_sources",
        "agent_state",
        "turn_markers",
        "ledger_summary",
        "service_outage",
        "tool_repetition_guard",
        "user_prompt",
        "verification_scope",
        "cancel_event",
        "memory_store",
        "retrieved_memories",
        "conversation_id",
        "db_session_factory",
        "durable_deferrals",
    }


def test_agent_deps_accepts_a_toolset_via_skip_validation() -> None:
    sources = FunctionToolset[AgentDeps]()
    deps = AgentDeps(
        site_id="plasmodb",
        strategy_session=StrategySession(site_id="plasmodb"),
        tool_sources=sources,
        turn_markers=TurnMarkers(),
    )
    assert deps.tool_sources is sources


def test_agent_deps_refuses_a_build_with_no_turn_record() -> None:
    """Every deps names the turn's record, so no write lands on a copy."""
    with pytest.raises(ValidationError) as raised:
        AgentDeps.model_validate(
            {
                "site_id": "plasmodb",
                "strategy_session": StrategySession(site_id="plasmodb"),
            }
        )

    assert [error["loc"] for error in raised.value.errors()] == [("turn_markers",)]


def test_dispatch_deps_write_onto_the_turns_own_record() -> None:
    state = _build_state()
    deps = _deps(state, _build_context())

    deps.turn_markers.built = True
    deps.turn_markers.record_eda_dataset_opened("DS_1")

    assert state.turn_markers.built is True
    assert state.turn_markers.eda_datasets_opened == ["DS_1"]


def test_dispatch_deps_copy_state_into_scratchpad() -> None:
    ctx = _build_context()
    state = _build_state()
    overview = SearchOverview(
        search_name="GenesByExpression",
        display_name="Genes by Expression",
        record_type="transcript",
        description="",
        parameter_names=["dataset"],
        required_params=["dataset"],
    )
    state = state.model_copy(
        update={
            "domain": StrategyDomainState(
                discovered_searches={"GenesByExpression": overview},
            ),
        },
    )
    deps = _deps(state, ctx)
    assert deps.site_id == ctx.site_id
    assert deps.user_id == ctx.user_id
    assert deps.strategy_session is ctx.strategy_session
    assert deps.tool_sources is None
    discovered = state.domain.discovered_searches
    assert deps.agent_state.discovered_searches == discovered
    assert deps.agent_state.discovered_searches is not discovered


def test_dispatch_deps_propagate_cancel_event_from_context() -> None:
    event = asyncio.Event()
    ctx = _build_context(cancel_event=event)
    deps = _deps(_build_state(), ctx)
    assert deps.cancel_event is event


def test_dispatch_deps_yield_a_fresh_tool_repetition_guard() -> None:
    ctx = _build_context()
    state = _build_state()
    deps_a = _deps(state, ctx)
    deps_b = _deps(state, ctx)
    assert deps_a.tool_repetition_guard is not deps_b.tool_repetition_guard


def test_context_is_a_frozen_dataclass() -> None:
    ctx = _build_context()
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.__setattr__("site_id", "different")


def test_agent_deps_keeps_existing_agent_tool_state_type() -> None:
    state = _build_state()
    ctx = _build_context()
    deps = _deps(state, ctx)
    assert isinstance(deps.agent_state, AgentToolState)
