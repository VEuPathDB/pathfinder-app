"""The seam between the guard mechanisms and the tools they watch.

Both guards key on tool names. The names are PathFinder's, so they arrive as
constructor arguments; a guard built with no vocabulary watches nothing rather
than watching another product's tools by accident. Every watched name must be
a tool one of the four agents offers, or the guard watches nothing that runs.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from assistant_core.capabilities import repetition_guard
from assistant_core.capabilities.repetition_guard import (
    DEFAULT_REPETITION_THRESHOLD,
    ToolRepetitionGuard,
)
from assistant_core.graph.runtime import AssistantDeps
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.agents.tool_vocabulary import (
    READ_ONLY_TOOLS,
    SEARCH_LOOKUP_TOOLS,
    build_tool_repetition_guard,
)
from pathfinder.ai.capabilities import resilience
from pathfinder.ai.capabilities.resilience import ToolResilience
from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import BUILD_SUB_AGENT_BY_ROLE, LeadDeps
from pathfinder.assistants.pathfinder_spec import RESEARCH_TOOL_SOURCE
from pathfinder.domain.strategy.session import StrategySession

PRODUCT_NAMES = {
    "READ_ONLY_TOOLS",
    "SEARCH_LOOKUP_TOOLS",
    "_SEARCH_LOOKUP_TOOLS",
}


def _never_factory() -> AsyncSession:
    msg = "the seam test makes no database call"
    raise AssertionError(msg)


def _tool_names(toolset: AbstractToolset[Any]) -> set[str]:
    """Names a toolset offers, through however many wrappers it carries."""
    if isinstance(toolset, WrapperToolset):
        return _tool_names(toolset.wrapped)
    if isinstance(toolset, FunctionToolset):
        return set(toolset.tools)
    return set()


def _served_tool_names() -> set[str]:
    """The tools a declared source serves, under the prefix the runtime adds."""
    return {
        f"{RESEARCH_TOOL_SOURCE.name}_{tool}"
        for tool in RESEARCH_TOOL_SOURCE.tools or ()
    }


def _offered_tool_names() -> set[str]:
    """Every tool name the Lead or one of the sub-agents can call."""
    agents = [build_lead_agent()]
    agents.extend(build() for build in BUILD_SUB_AGENT_BY_ROLE.values())
    registered = {
        name
        for agent in agents
        for toolset in agent.toolsets
        for name in _tool_names(toolset)
    }
    return registered | _served_tool_names()


def _context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=_never_factory,
        cancel_event=asyncio.Event(),
    )


def _pipeline_state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
    )


def _lead_deps() -> LeadDeps:
    return LeadDeps(
        state=_pipeline_state(),
        intent=None,
        runtime=_context(),
        retrieved_memories=[],
    )


def test_the_repetition_guard_module_names_no_product_tool() -> None:
    assert PRODUCT_NAMES & set(vars(repetition_guard)) == set()


def test_the_resilience_module_names_no_product_tool() -> None:
    assert PRODUCT_NAMES & set(vars(resilience)) == set()


def test_a_guard_with_no_vocabulary_watches_nothing() -> None:
    guard = ToolRepetitionGuard()
    for _ in range(DEFAULT_REPETITION_THRESHOLD + 1):
        assert guard.check("get_strategy", {}) is None
    assert guard.total_blocked == 0


def test_a_guard_blocks_the_read_only_tools_it_was_given() -> None:
    guard = ToolRepetitionGuard(read_only_tools=frozenset({"peek"}))
    for _ in range(DEFAULT_REPETITION_THRESHOLD - 1):
        assert guard.check("peek", {}) is None
    assert guard.check("peek", {}) is not None


def test_a_guard_honors_the_threshold_it_was_given() -> None:
    guard = ToolRepetitionGuard(read_only_tools=frozenset({"peek"}), threshold=2)
    assert guard.check("peek", {}) is None
    assert guard.check("peek", {}) is not None


def test_a_tool_outside_the_vocabulary_clears_the_streak() -> None:
    guard = ToolRepetitionGuard(read_only_tools=frozenset({"peek"}))
    for _ in range(DEFAULT_REPETITION_THRESHOLD - 1):
        guard.check("peek", {})
    assert guard.check("poke", {}) is None
    assert guard.check("peek", {}) is None


def test_the_product_guard_carries_the_pathfinder_vocabulary() -> None:
    guard = build_tool_repetition_guard()
    assert guard.read_only_tools == READ_ONLY_TOOLS
    assert "get_strategy" in guard.read_only_tools


def test_every_watched_name_is_a_tool_some_agent_offers() -> None:
    """A watched name nothing carries is an entry that can never fire."""
    assert READ_ONLY_TOOLS - _offered_tool_names() == set()


def test_the_watched_research_names_carry_the_source_prefix() -> None:
    """The guard keys on the name the model calls, which the prefix decides."""
    assert _served_tool_names() <= READ_ONLY_TOOLS
    assert "web_search" not in READ_ONLY_TOOLS
    assert "literature_search" not in READ_ONLY_TOOLS


def test_every_search_lookup_name_is_a_tool_some_agent_offers() -> None:
    assert SEARCH_LOOKUP_TOOLS - _offered_tool_names() == set()


def test_the_generic_deps_default_to_a_guard_that_watches_nothing() -> None:
    deps = AssistantDeps(site_id="plasmodb")
    assert deps.tool_repetition_guard.read_only_tools == frozenset()


def test_the_product_deps_default_to_the_pathfinder_guard() -> None:
    deps = AgentDeps(
        site_id="plasmodb",
        strategy_session=StrategySession(site_id="plasmodb"),
    )
    assert deps.tool_repetition_guard.read_only_tools == READ_ONLY_TOOLS


def test_every_sub_agent_dispatch_builds_deps_under_the_product_guard() -> None:
    """One deps container serves all three sub-agents, built once per dispatch."""
    deps = agent_deps_for(_lead_deps())

    assert deps.tool_repetition_guard.read_only_tools == READ_ONLY_TOOLS
    assert deps.tool_repetition_guard.stopped_call_id == ""


def test_the_lead_deps_carry_the_product_guard() -> None:
    deps = LeadDeps(
        state=_pipeline_state(),
        intent=None,
        runtime=_context(),
        retrieved_memories=[],
    )

    assert deps.tool_repetition_guard.read_only_tools == READ_ONLY_TOOLS


def test_each_turn_gets_its_own_guard_state() -> None:
    """Two dispatches never share a streak, so one turn cannot stop the next."""
    first = agent_deps_for(_lead_deps()).tool_repetition_guard
    for _ in range(DEFAULT_REPETITION_THRESHOLD + 1):
        first.check("get_strategy", {})
    second = agent_deps_for(_lead_deps()).tool_repetition_guard

    assert first.stopped_call_id != second.stopped_call_id or first.total_blocked > 0
    assert second.total_blocked == 0
    assert second.check("get_strategy", {}) is None


def test_resilience_takes_its_search_lookup_tools_as_an_argument() -> None:
    capability = ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS)
    assert capability.search_lookup_tools == SEARCH_LOOKUP_TOOLS
    assert ToolResilience().search_lookup_tools == frozenset()
