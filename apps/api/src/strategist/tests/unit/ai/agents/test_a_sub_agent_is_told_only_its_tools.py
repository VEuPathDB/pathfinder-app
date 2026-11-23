from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition
from veupathdb.errors import WDKError

from strategist.ai.agents.execution import (
    _EXECUTION_INSTRUCTIONS,
    build_execution_agent,
)
from strategist.ai.agents.frame import _FRAME_INSTRUCTIONS, build_frame_agent
from strategist.ai.agents.strategy_instructions import base_system_prompt
from strategist.ai.agents.verification import build_verification_agent
from strategist.ai.capabilities.resilience import ToolResilience
from strategist.ai.lead.contract_messages import unbacked_digest_message
from strategist.domain.strategy.staleness import StaleBuild
from strategist.tests._support.tool_names import (
    foreign_names,
    held_tool_names,
    named_tools,
    served_tool_names,
)
from strategist.tests.unit.ai.tools.conftest import (
    agent_run_context,
    function_toolset_or_none,
)

_BUILDERS: dict[str, Callable[[], Agent[Any, Any]]] = {
    "execution": build_execution_agent,
    "verification": build_verification_agent,
    "frame": build_frame_agent,
}


def _resilience(agent: Agent[Any, Any]) -> ToolResilience:
    leaves: list[AbstractCapability[Any]] = []
    agent.root_capability.apply(leaves.append)
    [found] = [leaf for leaf in leaves if isinstance(leaf, ToolResilience)]
    return found


_CALLED = {
    "execution": "update_leaf_params",
    "verification": "get_estimated_size",
    "frame": "get_search_overview",
}


async def _directive(role: str, status: int) -> str:
    agent = _BUILDERS[role]()
    answered = await _resilience(agent).on_tool_execute_error(
        agent_run_context(),
        call=ToolCallPart(
            tool_name=_CALLED[role],
            args='{"search_name":"GenesByNothing"}',
            tool_call_id="tc_1",
        ),
        tool_def=ToolDefinition(name=_CALLED[role]),
        args={"search_name": "GenesByNothing"},
        error=WDKError("refused", status=status),
    )
    return str(answered)


@pytest.mark.parametrize("role", sorted(_BUILDERS))
def test_the_shared_base_prompt_names_only_tools_each_sub_agent_holds(
    role: str,
) -> None:
    agent = _BUILDERS[role]()

    assert foreign_names(base_system_prompt(agent_run_context()), agent) == []


def test_frame_is_told_how_to_retry_a_catalog_call() -> None:
    assert {"search_for_searches", "get_record_types"} <= named_tools(
        _FRAME_INSTRUCTIONS
    )


@pytest.mark.parametrize("role", ["execution", "verification"])
async def test_a_wdk_refusal_names_only_held_tools(role: str) -> None:
    agent = _BUILDERS[role]()

    for status in (404, 422):
        assert foreign_names(await _directive(role, status), agent) == []


async def test_frame_is_told_to_read_the_rejected_parameter() -> None:
    assert "get_parameter_options" in await _directive("frame", 422)
    assert "get_record_types" in await _directive("frame", 404)


def test_a_stale_build_names_no_tool() -> None:
    rendered = StaleBuild(changed_nodes=[("step_1", 10, 12)]).render()

    assert foreign_names(rendered, build_execution_agent()) == []
    assert "step_1: recorded 10 -> now 12" in rendered


def test_a_save_names_no_control_tool_verify_lacks() -> None:
    verification = build_verification_agent()
    [save] = [
        tool
        for toolset in verification.toolsets
        if (found := function_toolset_or_none(toolset)) is not None
        for name, tool in found.tools.items()
        if name == "save_gene_set"
    ]
    described = (
        f"{save.description}\n{json.dumps(save.tool_def.parameters_json_schema)}"
    )

    assert foreign_names(described, verification) == []


def test_an_unbacked_digest_names_no_research_tool_by_name() -> None:
    unserved = held_tool_names(build_verification_agent()) - served_tool_names()

    assert sorted(named_tools(unbacked_digest_message([])) - unserved) == []


def test_execution_is_told_no_retired_tool() -> None:
    retired = ("create_leaf_step", "combine_steps", "update_step", "undo_last_change")

    named = [
        name
        for name in retired
        if re.search(rf"(?<!\w){name}(?!\w)", _EXECUTION_INSTRUCTIONS)
    ]

    assert named == []
