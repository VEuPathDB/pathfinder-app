"""Shared scaffolding for the tool tests: contexts, toolset unwrapping, summaries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from assistant_core.platform.db import DBSessionFactory
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.wdk.wdk_models import WDKSearch, WDKSearchResponse
from veupathdb.wdk.wdk_parameters import WDKParameter, WDKStringParam
from veupathdb_mcp.catalog import search_inspection

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import detached_session
from pathfinder.tests._support.run_context import (
    lead_run_context,
    run_context_for,
    turn_runtime,
)


def detached_lead_context() -> RunContext[LeadDeps]:
    """A Lead run context whose session factory opens a database-less session."""
    return lead_run_context(db_session_factory=detached_session)


def agent_run_context(
    *,
    site_id: str = "plasmodb",
    agent_state: AgentToolState | None = None,
    strategy_session: StrategySession | None = None,
    db_session_factory: DBSessionFactory | None = None,
    tool_call_id: str | None = "call_1",
) -> RunContext[AgentDeps]:
    runtime = turn_runtime(site_id=site_id, strategy_session=strategy_session)
    deps = AgentDeps(
        site_id=site_id,
        user_id=runtime.user_id,
        strategy_session=runtime.strategy_session,
        cancel_event=runtime.cancel_event,
        db_session_factory=db_session_factory,
        agent_state=agent_state if agent_state is not None else AgentToolState(),
    )
    return run_context_for(deps, tool_call_id)


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


def wdk_param(
    name: str, *, dependent_params: list[str] | None = None
) -> WDKStringParam:
    """A WDK parameter carrying only the fields the tools read."""
    return WDKStringParam(name=name, dependent_params=dependent_params or [])


@dataclass
class SearchDetailsDouble:
    """A WDK client serving one search's parameters, recording each read's context."""

    parameters: list[WDKParameter]
    contexts: list[dict[str, str]] = field(default_factory=list)

    def _response(self, search_name: str) -> WDKSearchResponse:
        return WDKSearchResponse(
            search_data=WDKSearch(url_segment=search_name, parameters=self.parameters),
            validation=StepValidation(level="NONE", is_valid=False),
        )

    async def get_search_details(
        self, _record_type: str, search_name: str, *, expand_params: bool = True
    ) -> WDKSearchResponse:
        del expand_params
        return self._response(search_name)

    async def get_search_details_with_params(
        self,
        _record_type: str,
        search_name: str,
        context: dict[str, str],
        *,
        expand_params: bool = True,
    ) -> WDKSearchResponse:
        del expand_params
        self.contexts.append(context)
        return self._response(search_name)


def patch_search_details(
    monkeypatch: pytest.MonkeyPatch,
    *,
    parameters: list[WDKParameter],
    record_type: str = "transcript",
) -> SearchDetailsDouble:
    """Serve one search's parameter list to every catalog read."""
    client = SearchDetailsDouble(parameters=parameters)

    async def _resolve(*_args: object, **_kwargs: object) -> str:
        return record_type

    monkeypatch.setattr(search_inspection, "resolve_search_record_type", _resolve)
    monkeypatch.setattr(search_inspection, "get_wdk_client", lambda _site: client)
    return client
