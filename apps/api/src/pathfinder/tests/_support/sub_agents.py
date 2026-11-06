"""Helpers for tests that read or pin a per-dispatch sub-agent."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.filtered import FilteredToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.lead import sub_agent_tools
from pathfinder.tests._support.run_context import run_context_for


def toolset_tool_names(toolset: AbstractToolset[Any]) -> set[str]:
    """The names a toolset offers, through however many wrappers and filters it carries."""
    filters: list[FilteredToolset[Any]] = []
    while isinstance(toolset, WrapperToolset):
        if isinstance(toolset, FilteredToolset):
            filters.append(toolset)
        toolset = toolset.wrapped
    if not isinstance(toolset, FunctionToolset):
        return set()
    ctx = run_context_for(None)
    return {
        name
        for name, tool in toolset.tools.items()
        if all(f.filter_func(ctx, tool.tool_def) is True for f in filters)
    }


def agent_tool_names(agent: Agent[Any, Any]) -> set[str]:
    """Every tool name the agent can call, across all of its toolsets."""
    return {name for ts in agent.toolsets for name in toolset_tool_names(ts)}


def agent_info_of(agent: Agent[Any, Any]) -> AgentInfo:
    return AgentInfo(
        function_tools=[
            ToolDefinition(name=n) for n in sorted(agent_tool_names(agent))
        ],
        allow_text_output=True,
        output_tools=[],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
        instructions=None,
    )


@contextlib.contextmanager
def pinned_sub_agent(
    monkeypatch: pytest.MonkeyPatch,
    role: PhaseRole,
    **overrides: Any,
) -> Iterator[None]:
    """Run every dispatch of ``role`` on one agent, overridden as given.

    A dispatch builds its own agent, so a test that overrides one instance
    pins that instance into the factory map for the duration.
    """
    agent = sub_agent_tools.BUILD_SUB_AGENT_BY_ROLE[role]()
    monkeypatch.setitem(
        sub_agent_tools.BUILD_SUB_AGENT_BY_ROLE,
        role,
        lambda: agent,
    )
    with agent.override(**overrides):
        yield
