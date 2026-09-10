"""PathFinder, assembled as one assistant, still declares every part it needs."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.stream_parts.registry import (
    StreamPartRegistry,
)
from assistant_core.persistence.models import Conversation
from assistant_core.spec import TurnContextRequest, TurnStart
from langgraph.checkpoint.memory import InMemorySaver
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.assistants import pathfinder_spec
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.tool_sources import RESEARCH_MCP_SOURCE_ID
from pathfinder.services.wdk_identity import require_registered_wdk_login
from pathfinder.transport.http.routers.memories import MEMORY_ROUTE_KINDS


def test_the_registry_serves_pathfinder_by_default() -> None:
    registry = get_assistant_registry()

    assert registry.default_id == PATHFINDER_ASSISTANT_ID
    assert registry.resolve(PATHFINDER_ASSISTANT_ID).assistant_id == "pathfinder"


def test_its_graph_factory_builds_the_two_node_graph() -> None:
    compiled = build_pathfinder_spec().build_graph(InMemorySaver())

    assert set(compiled.get_graph().nodes) >= {"lead", "finalize_turn"}


def test_its_initial_state_is_a_pipeline_state() -> None:
    start = TurnStart(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        turn_message_id=uuid4(),
        turn_start_event_id=0,
        user_prompt="find kinases",
    )

    state = build_pathfinder_spec().build_initial_state(start)

    assert isinstance(state, PipelineState)
    assert state.user_prompt == "find kinases"
    assert state.domain.operational_spec is None


def _install_strategy(
    monkeypatch: pytest.MonkeyPatch,
    strategy: ConversationStrategyView,
) -> None:
    class _Session:
        async def __aenter__(self) -> _Session:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

    class _Repo:
        def __init__(self, _session: _Session) -> None:
            return None

        async def get_strategy(
            self, _conversation_id: UUID
        ) -> ConversationStrategyView:
            return strategy

    monkeypatch.setattr(pathfinder_spec, "async_session_factory", _Session)
    monkeypatch.setattr(pathfinder_spec, "ConversationRepository", _Repo)


async def test_its_turn_context_is_the_product_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_strategy(monkeypatch, ConversationStrategyView(experiment_id="exp_1"))
    sources = {"research": FunctionToolset[object]()}
    request = TurnContextRequest(
        conversation=Conversation(id=uuid4(), name="", site_id="plasmodb"),
        site_id="plasmodb",
        user_id=uuid4(),
        memory_store=None,
        cancel_event=asyncio.Event(),
        phase_models={"lead": "openai:gpt-5.6-luna"},
        phase_reasoning={},
        tool_sources=sources,
    )

    context = await build_pathfinder_spec().build_turn_context(request)

    assert isinstance(context, Context)
    assert context.site_id == "plasmodb"
    assert context.strategy_session is not None
    assert context.experiment_id == "exp_1"
    assert context.phase_models == {"lead": "openai:gpt-5.6-luna"}
    assert context.tool_sources == sources


def test_it_declares_the_research_source_by_the_id_this_deployment_admits() -> None:
    """The two research tools are served, so the assistant asks for the server."""
    declared = build_pathfinder_spec().tool_sources

    assert len(declared) == 1
    source = declared[0]
    assert source.name == "research"
    assert source.source_id == RESEARCH_MCP_SOURCE_ID
    assert source.tools == frozenset({"web_search", "literature_search"})
    # Absent by default, so a deployment that admits no such server still runs.
    assert source.required is False


def test_it_registers_the_strategy_and_the_eda_stream_parts() -> None:
    registry = StreamPartRegistry()
    hook = build_pathfinder_spec().register_stream_parts
    assert hook is not None

    hook(registry)

    kinds = registry.kinds()
    assert "data-graph-snapshot" in kinds
    assert "data-strategy-revision" in kinds
    assert {
        "data-eda.analysis-state",
        "data-eda.subset-preview",
        "data-eda.viz",
    } <= kinds


def test_its_mock_factory_returns_the_scripted_function_model() -> None:
    model = build_pathfinder_spec().build_mock_model()

    assert isinstance(model, FunctionModel)


def test_it_declares_the_product_memory_kinds() -> None:
    assert build_pathfinder_spec().memory_kinds == frozenset(
        {"gene_set", "strategy", "preference", "knowledge", "case"},
    )


def test_the_memories_route_publishes_exactly_the_declared_kinds() -> None:
    """A kind the spec declares but the route hides would be unreachable."""
    assert set(MEMORY_ROUTE_KINDS) == build_pathfinder_spec().memory_kinds


def test_it_declares_the_registered_wdk_login_requirement() -> None:
    assert build_pathfinder_spec().identity_gate is require_registered_wdk_login


def test_it_declares_the_state_types_its_checkpoints_carry() -> None:
    declared = set(build_pathfinder_spec().checkpoint_types)

    assert {"StrategyDomainState", "OperationalSpec", "BuildOutcome"} <= {
        t.__name__ for t in declared
    }
