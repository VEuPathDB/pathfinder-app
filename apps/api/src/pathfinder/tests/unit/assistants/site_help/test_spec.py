"""Site help declares a whole assistant, and declares nothing PathFinder owns."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from assistant_core.graph.turn_state import TurnState
from assistant_core.spec import TurnContextRequest, TurnStart
from langgraph.checkpoint.memory import InMemorySaver
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset

from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.assistants.site_help.spec import (
    SiteHelpTurnContext,
    build_deps,
    build_site_help_spec,
    build_turn_context,
)
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID
from pathfinder.platform.tool_sources import WDK_MCP_SOURCE_ID


def test_the_registry_serves_it_alongside_pathfinder() -> None:
    registry = get_assistant_registry()

    assert set(registry.ids()) == {"pathfinder", SITE_HELP_ASSISTANT_ID}
    assert registry.default_id == "pathfinder"
    assert registry.resolve(SITE_HELP_ASSISTANT_ID).assistant_id == "site_help"


def test_its_graph_is_one_agent_and_the_runtime_s_finalize() -> None:
    compiled = build_site_help_spec().build_graph(InMemorySaver())

    assert set(compiled.get_graph().nodes) >= {"agent", "finalize_turn"}
    assert "lead" not in compiled.get_graph().nodes


def _start() -> TurnStart:
    return TurnStart(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        turn_message_id=uuid4(),
        turn_start_event_id=0,
        user_prompt="which sites are there",
    )


def _request(
    tool_sources: Mapping[str, AbstractToolset[Any]] | None = None,
) -> TurnContextRequest:
    return TurnContextRequest(
        conversation=None,
        site_id="plasmodb",
        user_id=uuid4(),
        memory_store=None,
        cancel_event=asyncio.Event(),
        phase_models={},
        phase_reasoning={},
        tool_sources=tool_sources or {},
    )


def _state() -> TurnState:
    return build_site_help_spec().build_initial_state(_start())


def test_its_state_is_the_bare_turn_state() -> None:
    state = build_site_help_spec().build_initial_state(_start())

    assert type(state) is TurnState
    assert state.user_prompt == "which sites are there"


async def test_its_turn_context_carries_no_domain_session() -> None:
    context = await build_turn_context(_request())

    assert type(context) is SiteHelpTurnContext
    assert context.site_id == "plasmodb"
    assert context.tool_sources == {}


def test_it_declares_the_wdk_server_as_an_optional_tool_source() -> None:
    (declaration,) = build_site_help_spec().tool_sources

    assert declaration.name == "wdk"
    assert declaration.source_id == WDK_MCP_SOURCE_ID
    assert declaration.tools == frozenset(
        {"list_record_types", "search_for_searches", "run_control_tests_on_search"},
    )
    assert declaration.required is False
    assert declaration.always_approve == frozenset()


async def test_the_turn_s_resolved_sources_reach_the_agent_s_deps() -> None:
    served: FunctionToolset[Any] = FunctionToolset()

    context = await build_turn_context(_request(tool_sources={"wdk": served}))

    assert context.tool_sources == {"wdk": served}
    assert build_deps(_state(), context).tool_sources is not None


async def test_a_turn_that_resolved_nothing_hands_the_agent_no_toolset() -> None:
    context = await build_turn_context(_request())

    assert build_deps(_state(), context).tool_sources is None


def test_it_declares_no_identity_requirement_and_no_extras() -> None:
    spec = build_site_help_spec()

    assert spec.identity_gate is None
    assert spec.register_stream_parts is None
    assert spec.turn_epilogue is None
    assert spec.memory_kinds == frozenset()
    assert spec.checkpoint_types == ()


def test_its_mock_factory_returns_its_own_script() -> None:
    model = build_site_help_spec().build_mock_model()

    assert isinstance(model, FunctionModel)
