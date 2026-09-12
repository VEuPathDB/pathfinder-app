"""Site help as one assistant: a single agent over the bare turn state.

It declares no phases, no sub-agents, no domain state and no identity
requirement. The application's own session auth still applies.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from assistant_core.graph.runtime import TurnContext
from assistant_core.graph.single_agent import single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.mcp.declaration import ToolSourceDeclaration
from assistant_core.platform.db import async_session_factory
from assistant_core.quota import accumulate
from assistant_core.spec import AssistantSpec, TurnContextRequest, TurnStart
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic_ai.toolsets import AbstractToolset, CombinedToolset

from pathfinder.assistants.site_help.agent import SiteHelpDeps, build_site_help_agent
from pathfinder.assistants.site_help.mock import build_site_help_mock
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID
from pathfinder.platform.tool_sources import WDK_MCP_SOURCE_ID

# The catalog reads a service credential may make, and the one measurement the
# user is asked about. A deployment that admits no such server serves neither.
WDK_TOOL_SOURCE = ToolSourceDeclaration(
    name="wdk",
    source_id=WDK_MCP_SOURCE_ID,
    tools=frozenset(
        {"list_record_types", "search_for_searches", "run_control_tests_on_search"},
    ),
)


@dataclass(frozen=True, kw_only=True)
class SiteHelpTurnContext(TurnContext):
    """The runtime's per-turn resources, plus the sources this turn resolved."""

    tool_sources: Mapping[str, AbstractToolset[Any]] = field(default_factory=dict)


def build_initial_state(start: TurnStart) -> TurnState:
    return TurnState(**start.state_kwargs())


async def build_turn_context(request: TurnContextRequest) -> SiteHelpTurnContext:
    """The runtime's own per-turn resources, and this turn's tool sources."""
    return SiteHelpTurnContext(
        site_id=request.site_id,
        user_id=request.user_id,
        db_session_factory=async_session_factory,
        cancel_event=request.cancel_event,
        memory_store=request.memory_store,
        phase_models=dict(request.phase_models),
        phase_reasoning=dict(request.phase_reasoning),
        tool_sources=dict(request.tool_sources),
    )


def _one_toolset(
    sources: Mapping[str, AbstractToolset[Any]],
) -> AbstractToolset[Any] | None:
    """This turn's sources as one toolset, or nothing when none resolved."""
    if not sources:
        return None
    return CombinedToolset(list(sources.values()))


def build_deps(state: TurnState, context: SiteHelpTurnContext) -> SiteHelpDeps:
    return SiteHelpDeps(
        site_id=context.site_id,
        user_id=context.user_id,
        conversation_id=state.conversation_id,
        db_session_factory=context.db_session_factory,
        memory_store=context.memory_store,
        cancel_event=context.cancel_event,
        tool_sources=_one_toolset(context.tool_sources),
    )


async def charge_usage(user_id: UUID, tokens: int, cost_usd: Decimal) -> None:
    """Site-help turns count against the same monthly budget as any other."""
    if tokens == 0 and cost_usd == 0:
        return
    async with async_session_factory() as session:
        await accumulate(session, user_id=user_id, tokens=tokens, cost_usd=cost_usd)
        await session.commit()


def build_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[TurnState, SiteHelpTurnContext, TurnState, TurnState]:
    return single_agent_graph(
        checkpointer=checkpointer,
        state_type=TurnState,
        context_type=SiteHelpTurnContext,
        build_agent=build_site_help_agent,
        build_deps=build_deps,
        charge_usage=charge_usage,
    )


def build_site_help_spec() -> AssistantSpec:
    return AssistantSpec(
        assistant_id=SITE_HELP_ASSISTANT_ID,
        build_graph=build_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=build_site_help_mock,
        tool_sources=(WDK_TOOL_SOURCE,),
    )


__all__ = [
    "WDK_TOOL_SOURCE",
    "SiteHelpTurnContext",
    "build_deps",
    "build_graph",
    "build_initial_state",
    "build_site_help_spec",
    "build_turn_context",
    "charge_usage",
]
