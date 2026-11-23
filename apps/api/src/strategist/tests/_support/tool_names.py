from __future__ import annotations

import functools
import re
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.toolsets import DynamicToolset

from strategist.ai.audit import auditor
from strategist.ai.explore.explore_agent import build_explore_agent
from strategist.ai.graph import runtime
from strategist.ai.lead import lead_agent
from strategist.ai.lead.sub_agent_tools import BUILD_SUB_AGENT_BY_ROLE
from strategist.platform.tool_sources import RESEARCH_TOOL_SOURCE
from strategist.tests._support.sub_agents import agent_tool_names

_TURN_SOURCES: tuple[object, ...] = (
    lead_agent.turn_tool_sources,
    runtime.turn_tool_sources,
    auditor.turn_tool_sources,
)


RETIRED_TOOLS: frozenset[str] = frozenset(
    {"create_leaf_step", "combine_steps", "update_step", "undo_last_change"}
)

ALLOWED: tuple[tuple[str, str, str, str], ...] = (
    (
        "_model_reading",
        "remember",
        "`remember`: the message asks to keep",
        "an intent the message reader returns, not a tool it is told to call",
    ),
    (
        "execution",
        "clear_strategy",
        "call clear_strategy to remove every step",
        (
            "the Lead's branch of _delete_rules._the_way_to_clear; a building "
            "pass receives the other branch"
        ),
    ),
)


def allowed_in(text: str) -> frozenset[str]:
    return frozenset(tool for _, tool, sentence, _ in ALLOWED if sentence in text)


def served_tool_names() -> set[str]:
    return {
        f"{RESEARCH_TOOL_SOURCE.name}_{tool}"
        for tool in RESEARCH_TOOL_SOURCE.tools or ()
    }


def _serves_research(agent: Agent[Any, Any]) -> bool:
    return any(
        isinstance(toolset, DynamicToolset) and toolset.toolset_func in _TURN_SOURCES
        for toolset in agent.toolsets
    )


def held_tool_names(agent: Agent[Any, Any]) -> frozenset[str]:
    served = served_tool_names() if _serves_research(agent) else set()
    return frozenset(agent_tool_names(agent) | served)


@functools.cache
def all_tool_names() -> frozenset[str]:
    agents: list[Agent[Any, Any]] = [
        lead_agent.build_lead_agent(),
        build_explore_agent(),
        auditor.build_auditor_agent(),
        *(build() for build in BUILD_SUB_AGENT_BY_ROLE.values()),
    ]
    held = {name for agent in agents for name in held_tool_names(agent)}
    return frozenset(held | served_tool_names())


def _mention(name: str) -> re.Pattern[str]:
    if "_" in name:
        return re.compile(rf"(?<![\w.\-/]){re.escape(name)}(?![\w=]|:\S)")
    return re.compile(rf"`{re.escape(name)}`|(?<![\w.\-/]){re.escape(name)}\(")


@functools.cache
def _mentions() -> tuple[tuple[str, re.Pattern[str]], ...]:
    vocabulary = all_tool_names() | RETIRED_TOOLS
    return tuple((name, _mention(name)) for name in sorted(vocabulary))


def named_tools(text: str) -> frozenset[str]:
    return frozenset(name for name, found in _mentions() if found.search(text))


def foreign_names(text: str, agent: Agent[Any, Any]) -> list[str]:
    return sorted(named_tools(text) - held_tool_names(agent))
