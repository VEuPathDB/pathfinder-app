"""No tool schema a model sees offers the held kind of a parameter value."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai.toolsets.abstract import AbstractToolset

from strategist.ai.explore.explore_agent import build_explore_toolset
from strategist.ai.lead.lead_agent import build_lead_toolset, build_sweep_toolset
from strategist.ai.tools.toolsets import eda, execution, frame, verification
from strategist.tests.unit.ai.tools.conftest import unwrap_function_toolset

_TOOLSETS: dict[str, Callable[[], AbstractToolset[Any]]] = {
    "lead": build_lead_toolset,
    "sweep": build_sweep_toolset,
    "explore": build_explore_toolset,
    "frame": frame.build_toolset,
    "execution": execution.build_toolset,
    "verification": verification.build_toolset,
    "eda": eda.build_toolset,
}


@pytest.mark.parametrize("name", sorted(_TOOLSETS))
def test_no_tool_schema_offers_a_held_value(name: str) -> None:
    tools = unwrap_function_toolset(_TOOLSETS[name]()).tools
    offering = sorted(
        tool_name
        for tool_name, tool in tools.items()
        if '"held"' in json.dumps(tool.tool_def.parameters_json_schema)
    )

    assert tools
    assert offering == []
