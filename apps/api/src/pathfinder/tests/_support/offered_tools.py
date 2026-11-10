from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.ai.audit.auditor import build_auditor_agent
from pathfinder.ai.explore.explore_agent import build_explore_agent
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import BUILD_SUB_AGENT_BY_ROLE
from pathfinder.platform.tool_sources import RESEARCH_TOOL_SOURCE


def _tool_names(toolset: AbstractToolset[Any]) -> set[str]:
    if isinstance(toolset, WrapperToolset):
        return _tool_names(toolset.wrapped)
    if isinstance(toolset, FunctionToolset):
        return set(toolset.tools)
    return set()


def served_tool_names() -> set[str]:
    return {
        f"{RESEARCH_TOOL_SOURCE.name}_{tool}"
        for tool in RESEARCH_TOOL_SOURCE.tools or ()
    }


def offered_tool_names() -> set[str]:
    agents: list[Agent[Any, Any]] = [
        build_lead_agent(),
        build_explore_agent(),
        build_auditor_agent(),
    ]
    agents.extend(build() for build in BUILD_SUB_AGENT_BY_ROLE.values())
    registered = {
        name
        for agent in agents
        for toolset in agent.toolsets
        for name in _tool_names(toolset)
    }
    return registered | served_tool_names()
