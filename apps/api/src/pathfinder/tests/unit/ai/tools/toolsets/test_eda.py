"""The EDA toolset, and the Lead that carries it."""

from __future__ import annotations

import json
import re

from pydantic_ai.messages import ToolReturnPart

from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.tools.standalone import eda_analysis, eda_catalog
from pathfinder.ai.tools.standalone._eda_models import (
    EdaStudyCardOut,
    EdaStudySearchResult,
)
from pathfinder.ai.tools.toolsets.eda import build_toolset
from pathfinder.tests.unit.ai.tools.conftest import unwrap_function_toolset

_EDA_TOOLS = {
    "search_eda_studies",
    "describe_eda_study",
    "open_eda_analysis",
    "set_eda_filters",
    "preview_eda_subset",
    "run_eda_compute",
    "create_eda_step",
}


def test_the_toolset_carries_exactly_the_seven_contract_tools() -> None:
    tools = unwrap_function_toolset(build_toolset()).tools
    assert set(tools) == _EDA_TOOLS


def test_the_durable_tool_is_registered_sequential() -> None:
    """One parked durable call is checkpointed per turn."""
    tools = unwrap_function_toolset(build_toolset()).tools
    assert tools["run_eda_compute"].sequential is True


def test_no_other_eda_tool_is_sequential() -> None:
    """A barrier on a plain tool costs a round trip for nothing."""
    tools = unwrap_function_toolset(build_toolset()).tools
    sequential = {name for name, tool in tools.items() if tool.sequential}
    assert sequential == {"run_eda_compute"}


_THRESHOLD_ARGUMENTS = (
    "effect_size_threshold",
    "significance_threshold",
    "effect_direction",
)


def test_create_eda_step_prose_names_its_three_threshold_arguments() -> None:
    """The volcano cut is the model's to set, so the prose must name it."""
    tools = unwrap_function_toolset(build_toolset()).tools
    description = tools["create_eda_step"].description or ""
    missing = [name for name in _THRESHOLD_ARGUMENTS if name not in description]
    assert missing == []


def test_both_plot_tools_declare_a_caption_argument() -> None:
    """The model writes the figure's caption, so the schema must offer it."""
    tools = unwrap_function_toolset(build_toolset()).tools
    for name in ("preview_eda_subset", "run_eda_compute"):
        properties = tools[name].function_schema.json_schema["properties"]
        assert "caption" in properties, name


def test_the_lead_agent_carries_the_eda_toolset() -> None:
    agent = build_lead_agent()
    names: set[str] = set()
    for toolset in agent.toolsets:
        names |= set(unwrap_function_toolset(toolset).tools)
    assert names >= _EDA_TOOLS


def test_no_eda_tool_name_collides_with_a_lead_tool() -> None:
    agent = build_lead_agent()
    seen: list[str] = []
    for toolset in agent.toolsets:
        seen.extend(unwrap_function_toolset(toolset).tools)
    assert len(seen) == len(set(seen))


_RETURNED_FIELDS_IN_SNAKE_CASE = (
    "dataset_id",
    "entity_id",
    "variable_id",
    "filter_type",
    "is_multi_valued",
    "can_export_rows",
    "sub_filter_variable_ids",
)

_DOCUMENTED_TOOLS = (
    eda_catalog.search_eda_studies,
    eda_catalog.describe_eda_study,
    eda_analysis.open_eda_analysis,
    eda_analysis.set_eda_filters,
    eda_analysis.preview_eda_subset,
)


def test_a_tool_return_reaches_the_model_in_camel_case() -> None:
    """pydantic-ai dumps a tool return by alias, so the model reads datasetId."""
    part = ToolReturnPart(
        tool_name="search_eda_studies",
        content=EdaStudySearchResult(
            studies=[
                EdaStudyCardOut(
                    dataset_id="DS_53f554ec6a",
                    study_id="STUDY_53f554ec6a",
                    display_name="Rodent malaria phenotypes",
                    can_export_rows=True,
                )
            ]
        ),
        tool_call_id="call-1",
    )
    card = json.loads(part.model_response_str())["studies"][0]
    assert card["datasetId"] == "DS_53f554ec6a"
    assert card["canExportRows"] is True
    assert "dataset_id" not in card


def test_a_tool_argument_reaches_the_model_in_snake_case() -> None:
    """The model writes the parameter names, so the two casings must not be merged."""
    tools = unwrap_function_toolset(build_toolset()).tools
    schema = tools["open_eda_analysis"].function_schema.json_schema
    assert set(schema["properties"]) == {"dataset_id", "purpose"}


def test_no_docstring_names_a_returned_field_in_snake_case() -> None:
    """A docstring saying dataset_id sends the model at a field the wire lacks.

    A name the tool also declares as an argument is exempt: the model writes
    those in snake_case, and the prose that asks for one says so.
    """
    tools = unwrap_function_toolset(build_toolset()).tools
    for tool in _DOCUMENTED_TOOLS:
        doc = tool.__doc__
        assert doc is not None
        prose = doc.split("Args:")[0]
        declared = set(tools[tool.__name__].function_schema.json_schema["properties"])
        named = [
            name
            for name in _RETURNED_FIELDS_IN_SNAKE_CASE
            if re.search(rf"\b{name}\b", prose) and name not in declared
        ]
        assert named == [], f"{tool.__name__} prose names {named}"
