"""The parameter sweep hangs off the Lead, with a stated reason to reach for it."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.tools.toolsets._dynamic import DynamicEnumToolset
from pathfinder.ai.tools.toolsets.verification import build_toolset
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.parameter_optimization.config import (
    SWEEP_BUDGET_MAX,
    SWEEP_MCC_FLOOR,
    SWEEP_RECALL_FLOOR,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.sub_agents import agent_tool_names, toolset_tool_names
from pathfinder.tests.unit.ai.tools.conftest import unwrap_function_toolset

SWEEP = "optimize_search_parameters"


def _verification_tools() -> dict[str, Any]:
    toolset = unwrap_function_toolset(build_toolset())
    return {tool.name: tool for tool in toolset.tools.values()}


def test_one_surface_owns_the_sweep() -> None:
    """The Lead offers it; VERIFY offers it no longer."""
    offered = (
        SWEEP in agent_tool_names(build_lead_agent()),
        SWEEP in _verification_tools(),
    )

    assert offered == (True, False)


def _lead_tool(name: str) -> Any:
    for mounted in build_lead_agent().toolsets:
        toolset = mounted
        while isinstance(toolset, WrapperToolset):
            toolset = toolset.wrapped
        if isinstance(toolset, FunctionToolset) and name in toolset.tools:
            return toolset.tools[name]
    return pytest.fail(f"the Lead offers no tool called {name}")


def test_the_sweep_is_sequential_and_gated_on_the_users_yes() -> None:
    tool = _lead_tool(SWEEP)

    assert tool.requires_approval is True
    assert tool.sequential is True


def test_verifys_instructions_no_longer_name_the_sweep() -> None:
    assert _VERIFICATION_INSTRUCTIONS.count(SWEEP) == 0


def test_the_operating_loop_states_both_floors() -> None:
    floors = (
        f"recall below {SWEEP_RECALL_FLOOR}, or MCC below {SWEEP_MCC_FLOOR} "
        "when the summary reports one"
    )

    assert LEAD_INSTRUCTIONS.count(floors) == 1
    assert LEAD_INSTRUCTIONS.count(SWEEP) == 1


def test_the_budget_carries_the_ceiling_the_config_states() -> None:
    budget = _lead_tool(SWEEP).function_schema.json_schema["properties"]["budget"]

    assert (budget["minimum"], budget["maximum"]) == (2, SWEEP_BUDGET_MAX)


async def test_the_step_id_is_an_enum_of_the_strategys_live_steps() -> None:
    session = StrategySession(site_id="plasmodb")
    session.sync_state = WDKSyncState(wdk_step_ids={"a": 440230693, "b": 440230653})
    mounted = [
        toolset
        for toolset in build_lead_agent().toolsets
        if isinstance(toolset, DynamicEnumToolset)
        and SWEEP in toolset_tool_names(toolset)
    ]

    offered = await mounted[0].get_tools(
        lead_run_context(strategy_session=session),
    )
    schema = offered[SWEEP].tool_def.parameters_json_schema

    assert schema["properties"]["wdk_step_id"]["enum"] == [440230653, 440230693]


def test_the_floors_are_the_numbers_the_design_named() -> None:
    assert (SWEEP_RECALL_FLOOR, SWEEP_MCC_FLOOR) == (0.7, 0.3)
