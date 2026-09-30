"""The sample cap is in the schema the model fills, and a limit past it is
refused with the cap."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.ai.tools.toolsets.verification import build_toolset
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


@pytest.mark.asyncio
async def test_the_limit_carries_its_cap_and_a_limit_past_it_names_the_cap() -> None:
    tools = await build_toolset().get_tools(agent_run_context())
    sample = tools["get_sample_records"]

    schema = sample.tool_def.parameters_json_schema["properties"]["limit"]
    with pytest.raises(ValidationError) as refused:
        sample.args_validator.validate_python({"wdk_step_id": 441030803, "limit": 1000})

    assert (schema["minimum"], schema["maximum"]) == (1, 100)
    assert "less than or equal to 100" in str(refused.value)
