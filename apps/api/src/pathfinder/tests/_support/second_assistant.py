"""A one-agent assistant the tests install beside PathFinder, and how to install it."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from assistant_core.graph.runtime import AssistantDeps, TurnContext
from assistant_core.graph.single_agent import SingleAgent, single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.mcp.declaration import ToolSourceDeclaration
from assistant_core.models.scripted import (
    RoleMarkers,
    ScriptedModel,
    ScriptedPart,
    current_turn,
    last_user_text,
    scripted_call,
    scripted_text,
    tool_return_parts,
    user_texts,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.quota import accumulate
from assistant_core.spec import AssistantSpec, TurnContextRequest, TurnStart
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.tools import RunContext
from pydantic_ai.toolsets import AbstractToolset, CombinedToolset
from veupathdb_mcp.catalog import list_sites

from pathfinder.assistants import registry
from pathfinder.assistants.registry import InstalledAssistant
from pathfinder.platform.model_catalog import DEFAULT_MODEL_ID
from pathfinder.platform.model_keys import turn_paid_by
from pathfinder.platform.tool_sources import WDK_MCP_SOURCE_ID

HELPER = "helper"
HELPER_MODEL = DEFAULT_MODEL_ID

WDK_TOOL_SOURCE = ToolSourceDeclaration(
    name="wdk",
    source_id=WDK_MCP_SOURCE_ID,
    tools=frozenset(
        {"list_record_types", "search_for_searches", "run_control_tests_on_search"},
    ),
)

LIST_SITES_TOOL = "list_site_ids"
WDK_RECORD_TYPES_TOOL = "wdk_list_record_types"
WDK_CONTROL_TESTS_TOOL = "wdk_run_control_tests_on_search"
WDK_CONTROL_TESTS_CALL_ID = "call_wdk_control_tests"

CHECK_PROMPT = "helper check"
CHECK_REPLY = "The helper is online."
SITES_PROMPT = "which sites can I search"
SITES_REPLY = "Those are the sites I can reach."
RECORD_TYPES_PROMPT = "what record types does plasmodb serve"
RECORD_TYPES_REPLY = "Those are the record types that site serves."
CONTROL_TESTS_PROMPT = "run a control test on the molecular weight search"
CONTROL_TESTS_REPLY = "The control test is done."
PROCEED_PROMPT = "Yes, please proceed."
PROCEED_PREFIX = "Proceeding with: "

_REPLY_AFTER = {
    LIST_SITES_TOOL: SITES_REPLY,
    WDK_RECORD_TYPES_TOOL: RECORD_TYPES_REPLY,
    WDK_CONTROL_TESTS_TOOL: CONTROL_TESTS_REPLY,
}


class HelperDeps(AssistantDeps):
    tool_sources: AbstractToolset[Any] | None = None


@dataclass(frozen=True, kw_only=True)
class HelperTurnContext(TurnContext):
    tool_sources: Mapping[str, AbstractToolset[Any]] = field(default_factory=dict)


def build_initial_state(start: TurnStart) -> TurnState:
    return TurnState(**start.state_kwargs())


async def build_turn_context(request: TurnContextRequest) -> HelperTurnContext:
    return HelperTurnContext(
        site_id=request.site_id,
        user_id=request.user_id,
        db_session_factory=async_session_factory,
        cancel_event=request.cancel_event,
        memory_store=request.memory_store,
        phase_models=dict(request.phase_models),
        phase_reasoning=dict(request.phase_reasoning),
        tool_sources=dict(request.tool_sources),
    )


def build_deps(state: TurnState, context: HelperTurnContext) -> HelperDeps:
    sources = list(context.tool_sources.values())
    return HelperDeps(
        site_id=context.site_id,
        user_id=context.user_id,
        conversation_id=state.conversation_id,
        db_session_factory=context.db_session_factory,
        memory_store=context.memory_store,
        cancel_event=context.cancel_event,
        tool_sources=CombinedToolset(sources) if sources else None,
    )


async def charge_usage(user_id: UUID, tokens: int, cost_usd: Decimal) -> None:
    if tokens == 0 and cost_usd == 0:
        return
    async with async_session_factory() as session:
        await accumulate(
            session,
            user_id=user_id,
            tokens=tokens,
            cost_usd=cost_usd,
            paid_by=turn_paid_by(HELPER_MODEL),
        )
        await session.commit()


async def list_site_ids() -> list[str]:
    """List the id of every VEuPathDB site this deployment can reach."""
    return [site.id for site in await list_sites()]


def turn_tool_sources(ctx: RunContext[HelperDeps]) -> AbstractToolset[Any] | None:
    return ctx.deps.tool_sources


def _call_for(lowered: str) -> ScriptedPart | None:
    if "which sites" in lowered:
        return scripted_call(LIST_SITES_TOOL, {})
    if "control test" in lowered:
        return ToolCallPart(
            tool_name=WDK_CONTROL_TESTS_TOOL,
            args={
                "site_id": "plasmodb",
                "target_search_name": "GenesByMolecularWeight",
                "target_parameters": {},
                "positive_controls": ["PF3D7_1222600"],
            },
            tool_call_id=WDK_CONTROL_TESTS_CALL_ID,
        )
    if "record types" in lowered:
        return scripted_call(WDK_RECORD_TYPES_TOOL, {"site_id": "plasmodb"})
    return None


def _helper_script(messages: list[ModelMessage]) -> ScriptedPart:
    turn = current_turn(messages)
    for part in tool_return_parts(turn):
        if part.tool_name in _REPLY_AFTER:
            return scripted_text(_REPLY_AFTER[part.tool_name])
    text = last_user_text(turn)
    lowered = text.lower()
    if CHECK_PROMPT in lowered:
        return scripted_text(CHECK_REPLY)
    if "please proceed" in lowered:
        return scripted_text(f"{PROCEED_PREFIX}{user_texts(messages)[:-1][-1]}")
    called = _call_for(lowered)
    return called if called is not None else scripted_text(f"[mock] {text}")


def _title_script(messages: list[ModelMessage]) -> ScriptedPart:
    lines = last_user_text(messages).splitlines()
    return scripted_text(lines[-1] if lines else "")


_SCRIPT = ScriptedModel(
    roles=(RoleMarkers(role=HELPER, markers=frozenset({LIST_SITES_TOOL})),),
    scripts={HELPER: _helper_script},
    unknown=_title_script,
)


def build_helper_mock() -> FunctionModel:
    return _SCRIPT.as_function_model()


def build_helper_agent() -> Agent[HelperDeps, str]:
    return Agent(
        build_helper_mock(),
        output_type=str,
        deps_type=HelperDeps,
        instructions="Answer the researcher with the tools this turn offers.",
        tools=[Tool(list_site_ids)],
        toolsets=[turn_tool_sources],
        name=HELPER,
        defer_model_check=True,
    )


def build_helper_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[TurnState, HelperTurnContext, TurnState, TurnState]:
    return single_agent_graph(
        checkpointer=checkpointer,
        state_type=TurnState,
        context_type=HelperTurnContext,
        agent=SingleAgent(
            build_agent=build_helper_agent,
            build_deps=build_deps,
        ),
        charge_usage=charge_usage,
    )


def build_helper_spec() -> AssistantSpec:
    return AssistantSpec(
        assistant_id=HELPER,
        build_graph=build_helper_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=build_helper_mock,
        tool_sources=(WDK_TOOL_SOURCE,),
    )


def _helper_models() -> dict[str, str]:
    return {HELPER: HELPER_MODEL}


@contextmanager
def second_assistant(
    monkeypatch: pytest.MonkeyPatch,
    build_spec: Callable[[], AssistantSpec] = build_helper_spec,
) -> Iterator[None]:
    production = registry.installed_assistants()
    helper = InstalledAssistant(
        build_spec=build_spec,
        compile_time_models=_helper_models,
        prompt_role=HELPER,
        turn_roles=frozenset({HELPER}),
    )
    monkeypatch.setattr(
        registry, "installed_assistants", lambda: {**production, HELPER: helper}
    )
    registry.get_assistant_registry.cache_clear()
    try:
        yield
    finally:
        registry.get_assistant_registry.cache_clear()
