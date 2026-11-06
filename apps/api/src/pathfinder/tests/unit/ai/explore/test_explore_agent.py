from __future__ import annotations

import inspect
from typing import Any

import pytest
from assistant_core.models.scripted import detect_role
from pydantic import SecretStr
from pydantic_ai import Tool
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.explore.explore_agent import (
    build_explore_agent,
    build_explore_toolset,
)
from pathfinder.ai.explore.explore_model import resolve_explore_model_context
from pathfinder.ai.models.mock import _ROLES
from pathfinder.ai.tools.standalone import catalog_discovery
from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import attach_keyring
from pathfinder.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)
from pathfinder.tests._support.sub_agents import agent_info_of, agent_tool_names
from pathfinder.tests.unit.ai.tools.conftest import unwrap_function_toolset

TERRA = "openai:gpt-6.1-terra"
FABLE = "anthropic:claude-fable-5-1"


@pytest.fixture
def _cloud_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "deployment-openai")
    monkeypatch.setattr(settings, "default_provider", "openai", raising=False)


def _explore_tools() -> FunctionToolset[Any]:
    return unwrap_function_toolset(build_explore_toolset())


def test_explore_holds_no_tool_that_writes_the_strategy() -> None:
    names = agent_tool_names(build_explore_agent())

    assert {
        "propose_readings",
        "consult_user",
        "search_for_searches",
        "get_search_overview",
        "get_parameter_options",
        "read_gene_record",
        "get_live_strategy_state",
        "list_gene_sets",
        "search_memory",
        "remember",
        "run_eda_compute",
        "run_eda_dimensionality_reduction",
        "optimize_search_parameters",
    } <= names
    assert names.isdisjoint(
        {
            "frame_problem",
            "build_strategy",
            "edit_strategy",
            "verify_strategy",
            "recover_failed_steps",
            "create_eda_step",
            "propose_changes",
            "clear_strategy",
            "delete_step",
            "separate_controls",
            "adopt_separating_strategy",
            "save_gene_set",
            "export_gene_set",
            "rename_strategy",
        }
    )


def test_the_readings_card_needs_the_researchers_yes() -> None:
    tools = _explore_tools().tools

    assert [n for n, t in sorted(tools.items()) if t.requires_approval] == [
        "consult_user"
    ]


def test_a_catalog_read_keeps_the_description_of_the_tool_it_wraps() -> None:
    tools = _explore_tools().tools
    described = tools["get_search_overview"].description or ""

    assert described.startswith(
        "Get a high-level overview of a search: description, parameters"
    )
    assert "search_name: WDK search name" in described


def test_a_catalog_read_describes_only_the_arguments_it_takes() -> None:
    tool: Tool[Any] = _explore_tools().tools["get_parameter_options"]
    described = tool.description or ""
    original = inspect.getdoc(catalog_discovery.get_parameter_options) or ""

    assert "requirement:" in original
    assert "ctx:" in original
    assert "requirement" not in described
    assert "ctx:" not in described
    assert "context_values: Current values of the parent parameters" in described
    assert set(tool.function_schema.json_schema["properties"]) == {
        "search_name",
        "parameter_id",
        "record_type",
        "context_values",
        "query",
    }


def test_the_mock_reads_explore_as_its_own_role() -> None:
    assert detect_role(agent_info_of(build_explore_agent()), _ROLES) == "explore"


@pytest.mark.usefixtures("_cloud_provider")
def test_explore_runs_on_terra_by_default() -> None:
    resolved = resolve_explore_model_context(
        build_explore_agent(), model_override=None, reasoning_effort=None
    )

    assert resolved.model_id == TERRA


@pytest.mark.usefixtures("_cloud_provider")
def test_a_picked_explore_model_wins() -> None:
    own = ProviderKeyring(active={"anthropic": SecretStr("sk-ant-user-sentinel-0")})

    with attach_keyring(own, build=ProviderWire().build):
        resolved = resolve_explore_model_context(
            build_explore_agent(), model_override=FABLE, reasoning_effort="high"
        )

    assert (resolved.model_id, resolved.reasoning_effort) == (FABLE, "high")


def test_the_mock_deployment_runs_the_mock_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        get_settings(), "pathfinder_chat_provider", "mock", raising=False
    )

    resolved = resolve_explore_model_context(
        build_explore_agent(), model_override=None, reasoning_effort=None
    )

    assert (resolved.model_id, resolved.reasoning_effort) == ("mock:explore", None)


def test_a_readings_count_takes_two_readings_at_least() -> None:
    schema = _explore_tools().tools["propose_readings"].function_schema.json_schema

    assert (schema["required"], schema["properties"]["readings"]["minItems"]) == (
        ["readings"],
        2,
    )
