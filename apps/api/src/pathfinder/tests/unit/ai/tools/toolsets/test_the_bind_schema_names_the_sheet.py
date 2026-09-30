"""The schema FRAME binds with names the parameters of every open sheet, and
the display names a parameter term may take."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._frame_sheet import open_parameter_sheet
from pathfinder.ai.tools.toolsets.frame import build_toolset
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_TEXT = suite_search("search_genes_by_text")
_PERCENTILE = suite_search("search_genes_by_rnaseq_gomez_diaz_percentile")


async def _bind_schema(state: AgentToolState) -> dict[str, Any]:
    tools = await build_toolset().get_tools(agent_run_context(agent_state=state))
    return tools["set_criterion"].tool_def.parameters_json_schema


def _params(schema: dict[str, Any]) -> dict[str, Any]:
    branches: list[dict[str, Any]] = schema["properties"]["params"]["anyOf"]
    [branch] = [b for b in branches if b["type"] == "object"]
    return branch


def _choice(schema: dict[str, Any], basis: str) -> dict[str, Any]:
    """The ``why`` branch of one basis, or the one object when no sheet is open."""
    choice: dict[str, Any] = schema["$defs"]["SearchChoice"]
    branches: list[dict[str, Any]] = choice.get("anyOf", [choice])
    return next(
        b
        for b in branches
        if basis
        in b["properties"]["basis"].get("enum", [b["properties"]["basis"].get("const")])
    )


def _term(schema: dict[str, Any]) -> str:
    description: str = _choice(schema, "parameter")["properties"]["term"]["description"]
    return description


@pytest.mark.asyncio
async def test_with_no_sheet_open_params_names_no_parameter() -> None:
    schema = await _bind_schema(AgentToolState())

    assert "properties" not in _params(schema)
    assert "open sheet" not in _term(schema)


@pytest.mark.asyncio
async def test_an_open_sheet_names_its_parameters_and_their_display_names() -> None:
    state = AgentToolState()
    open_parameter_sheet(state, "c_ves", _TEXT.url_segment, _TEXT)

    schema = await _bind_schema(state)

    params = _params(schema)
    assert sorted(params["properties"]) == [
        "text_expression",
        "text_fields",
        "text_search_organism",
    ]
    assert params["additionalProperties"] is False
    assert _term(schema).endswith(
        " With basis parameter, a display name of the open sheet: c_ves "
        "(GenesByText): Organism, Text term (use * as wildcard), Fields."
    )


@pytest.mark.asyncio
async def test_two_open_sheets_name_every_parameter_either_holds() -> None:
    state = AgentToolState()
    open_parameter_sheet(state, "c_ves", _TEXT.url_segment, _TEXT)
    open_parameter_sheet(state, "c_blood", _PERCENTILE.url_segment, _PERCENTILE)

    schema = await _bind_schema(state)

    assert sorted(_params(schema)["properties"]) == [
        "any_or_all",
        "channel",
        "max_expression_percentile",
        "min_expression_percentile",
        "profileset_generic",
        "protein_coding_only",
        "samples_percentile_generic",
        "text_expression",
        "text_fields",
        "text_search_organism",
    ]
    assert f"c_blood ({_PERCENTILE.url_segment}): Experiment, Samples" in _term(schema)


@pytest.mark.asyncio
async def test_the_model_reads_the_open_sheets_parameters_at_the_step() -> None:
    state = AgentToolState()
    open_parameter_sheet(state, "c_ves", _TEXT.url_segment, _TEXT)
    seen: list[dict[str, Any]] = []

    def respond(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        [bind] = [t for t in info.function_tools if t.name == "set_criterion"]
        seen.append(bind.parameters_json_schema)
        return ModelResponse(parts=[TextPart("done")])

    deps = agent_run_context(agent_state=state).deps
    agent = Agent(
        FunctionModel(respond), deps_type=AgentDeps, toolsets=[build_toolset()]
    )
    await agent.run("bind the ves criterion", deps=deps)

    [schema] = seen
    assert sorted(_params(schema)["properties"]) == [
        "text_expression",
        "text_fields",
        "text_search_organism",
    ]


@pytest.mark.asyncio
async def test_a_parameter_term_is_one_name_of_the_open_sheet() -> None:
    """Two names joined in one term is no parameter, so the schema offers none."""
    state = AgentToolState()
    open_parameter_sheet(state, "c_ves", _TEXT.url_segment, _TEXT)

    schema = await _bind_schema(state)

    parameter = _choice(schema, "parameter")
    assert parameter["properties"]["basis"]["const"] == "parameter"
    assert parameter["properties"]["term"]["enum"] == [
        "Fields",
        "Organism",
        "Text term (use * as wildcard)",
        "text_expression",
        "text_fields",
        "text_search_organism",
    ]


@pytest.mark.asyncio
async def test_every_other_basis_keeps_a_free_term() -> None:
    state = AgentToolState()
    open_parameter_sheet(state, "c_ves", _TEXT.url_segment, _TEXT)

    schema = await _bind_schema(state)

    other = _choice(schema, "organism")
    assert other["properties"]["basis"]["enum"] == [
        "organism",
        "record_type",
        "only_match",
        "nearest",
    ]
    assert "enum" not in other["properties"]["term"]
