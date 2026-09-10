"""Shared scaffolding for the tool tests: contexts, toolset unwrapping, summaries."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk
from pydantic_ai.usage import RunUsage
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.session import StrategySession
from veupathdb_mcp.catalog import search_inspection

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps


class SessionCM:
    """An async context manager standing in for a database session."""

    def __init__(self) -> None:
        self.session = MagicMock()
        self.session.commit = AsyncMock()

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, *_args: Any) -> bool:
        return False


def never_factory() -> AsyncSession:
    msg = "db factory should not be called in unit tests"
    raise AssertionError(msg)


def agent_state_ctx(
    state: AgentToolState | None = None, *, site_id: str = "plasmodb"
) -> Any:
    """A run context whose deps carry a site and an agent state."""
    ctx = MagicMock()
    ctx.tool_call_id = "call_1"
    ctx.deps = MagicMock()
    ctx.deps.site_id = site_id
    ctx.deps.agent_state = state if state is not None else AgentToolState()
    return ctx


def runtime_ctx(*, site_id: str = "plasmodb") -> Any:
    """A run context whose deps expose the turn runtime the Lead tools read."""
    ctx = MagicMock()
    ctx.tool_call_id = "call_1"
    ctx.deps = MagicMock()
    ctx.deps.runtime.site_id = site_id
    ctx.deps.runtime.user_id = uuid4()
    ctx.deps.runtime.db_session_factory = MagicMock(return_value=SessionCM())
    return ctx


def turn_runtime() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=never_factory,
        cancel_event=asyncio.Event(),
    )


def lead_deps(runtime: Context, *, user_prompt: str = "find kinases") -> LeadDeps:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=user_prompt,
        domain=StrategyDomainState(),
    )
    return LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])


def lead_run_context(
    *, user_prompt: str = "find kinases", tool_call_id: str | None = None
) -> RunContext[LeadDeps]:
    runtime = turn_runtime()
    return RunContext(
        deps=lead_deps(runtime, user_prompt=user_prompt),
        model=TestModel(),
        usage=RunUsage(),
        messages=[],
        tool_call_id=tool_call_id,
    )


def agent_run_context() -> RunContext[AgentDeps]:
    runtime = turn_runtime()
    deps = AgentDeps(
        site_id="plasmodb",
        user_id=runtime.user_id,
        strategy_session=runtime.strategy_session,
        cancel_event=runtime.cancel_event,
    )
    return RunContext(deps=deps, model=TestModel(), usage=RunUsage(), messages=[])


@pytest.fixture
def lead_ctx() -> RunContext[LeadDeps]:
    return lead_run_context()


@pytest.fixture
def agent_ctx() -> RunContext[AgentDeps]:
    return agent_run_context()


def unwrap_function_toolset(toolset: AbstractToolset[Any]) -> FunctionToolset[Any]:
    """The FunctionToolset under any number of wrapper layers."""
    found = function_toolset_or_none(toolset)
    assert found is not None
    return found


def function_toolset_or_none(
    toolset: AbstractToolset[Any],
) -> FunctionToolset[Any] | None:
    """The FunctionToolset under the wrappers, or nothing for a served source.

    A source resolved per turn holds no registered function, so a caller that
    reads the names an agent declares statically skips it.
    """
    while isinstance(toolset, WrapperToolset):
        toolset = toolset.wrapped
    if isinstance(toolset, FunctionToolset):
        return toolset
    return None


def summary_chunks(chunks: Sequence[BaseChunk]) -> list[DataChunk]:
    return [
        chunk
        for chunk in chunks
        if isinstance(chunk, DataChunk) and chunk.type == "data-tool-summary"
    ]


def summary_of(returned: ToolReturn[Any]) -> DataChunk:
    """The one summary chunk a tool put on its return."""
    found = summary_chunks(returned.metadata or [])
    assert len(found) == 1
    return found[0]


def wdk_param(name: str) -> Any:
    """A WDK parameter stub carrying only the fields the tools read."""
    param = MagicMock()
    param.name = name
    param.dependent_params = []
    return param


def patch_search_details(
    monkeypatch: pytest.MonkeyPatch,
    *,
    parameters: list[Any],
    record_type: str = "transcript",
) -> Any:
    """Serve one search's parameter list to every catalog read."""

    async def _resolve(*_args: Any, **_kwargs: Any) -> str:
        return record_type

    monkeypatch.setattr(search_inspection, "resolve_search_record_type", _resolve)
    details = MagicMock()
    details.search_data.parameters = parameters
    client = MagicMock()
    client.get_search_details = AsyncMock(return_value=details)
    client.get_search_details_with_params = AsyncMock(return_value=details)
    monkeypatch.setattr(search_inspection, "get_wdk_client", lambda _site: client)
    return client
