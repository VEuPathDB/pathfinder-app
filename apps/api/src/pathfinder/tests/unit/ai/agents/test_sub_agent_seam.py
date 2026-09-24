"""The seam between a sub-agent dispatch and the agent it runs.

A module-level agent is one agent for the whole process, so each phase module
exposes a factory instead and the agent belongs to the dispatch that runs it.
Its pinned instructions and its construction are checked here for the same
reason: the three phase agents must not drift apart.
"""

from __future__ import annotations

import inspect
import warnings
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from assistant_core.models.settings import baked_model_id
from pydantic_ai import Agent, PydanticAIDeprecationWarning, Tool
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.agents import (
    _instructions,
    execution,
    frame,
    strategy_instructions,
    verification,
)
from pathfinder.ai.agents.execution import EXECUTION_MODEL, build_execution_agent
from pathfinder.ai.agents.frame import FRAME_MODEL, build_frame_agent
from pathfinder.ai.agents.registry import phase_defaults
from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.agents.verification import (
    VERIFICATION_MODEL,
    build_verification_agent,
)
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import (
    BUILD_SUB_AGENT_BY_ROLE,
    SUB_AGENT_MODEL_BY_ROLE,
)
from pathfinder.tests._support.instructions import pinned_instructions
from pathfinder.tests._support.sub_agents import agent_tool_names

SCRATCHPAD_TOOL_NAMES = frozenset(
    {
        "delete_note",
        "list_notes",
        "note",
        "pin_note",
        "promote_to_memory",
        "read_note",
        "search_notes",
        "unpin_note",
        "update_note",
    }
)

FRAME_TOOL_NAMES = SCRATCHPAD_TOOL_NAMES | {
    "browse_search_categories",
    "drop_criterion",
    "get_ai_expression_summary",
    "get_parameter_options",
    "get_record_types",
    "get_search_overview",
    "get_strategy",
    "list_saved_strategies",
    "list_searches",
    "list_transforms",
    "lookup_gene_records",
    "lookup_phyletic_codes",
    "remember",
    "search_example_plans",
    "search_for_searches",
    "search_memory",
    "set_criterion",
    "set_structure",
    "think",
}

EXECUTION_TOOL_NAMES = SCRATCHPAD_TOOL_NAMES | {
    "add_step_analysis",
    "add_step_filter",
    "add_step_report",
    "apply_operations",
    "build_strategy",
    "delete_step",
    "get_strategy",
    "insert_saved_strategy",
    "remember",
    "rename_strategy",
    "replace_subtree",
    "request_search_inspection",
    "search_memory",
    "think",
    "update_combine_operator",
    "update_leaf_params",
    "update_step_metadata",
}

VERIFICATION_TOOL_NAMES = SCRATCHPAD_TOOL_NAMES | {
    "check_study_step",
    "create_workbench_gene_set",
    "export_gene_set",
    "get_ai_expression_summary",
    "get_confidence_scores",
    "get_download_url",
    "get_enrichment_results",
    "get_estimated_size",
    "get_evaluation_summary",
    "get_experiment_config",
    "get_result_gene_lists",
    "get_sample_records",
    "get_strategy",
    "list_workbench_gene_sets",
    "lookup_gene_records",
    "remember",
    "request_search_inspection",
    "resolve_gene_ids_to_records",
    "run_control_tests_on_search",
    "run_control_tests_on_step",
    "run_gene_set_enrichment",
    "search_memory",
    "think",
}

ROLES: tuple[PhaseRole, ...] = ("frame", "execution", "verification")

BUILDERS: dict[PhaseRole, Callable[[], Agent[Any, Any]]] = {
    "frame": build_frame_agent,
    "execution": build_execution_agent,
    "verification": build_verification_agent,
}

BAKED_MODELS: dict[PhaseRole, str] = {
    "frame": FRAME_MODEL,
    "execution": EXECUTION_MODEL,
    "verification": VERIFICATION_MODEL,
}

TOOL_NAMES: dict[PhaseRole, frozenset[str]] = {
    "frame": FRAME_TOOL_NAMES,
    "execution": EXECUTION_TOOL_NAMES,
    "verification": VERIFICATION_TOOL_NAMES,
}

SINGLETONS: tuple[tuple[ModuleType, str], ...] = (
    (frame, "frame_agent"),
    (execution, "execution_agent"),
    (verification, "verification_agent"),
)


async def stub_tool() -> str:
    return "stub"


@pytest.mark.parametrize(("module", "name"), SINGLETONS, ids=str)
def test_the_phase_module_owns_no_agent_singleton(
    module: ModuleType,
    name: str,
) -> None:
    assert [n for n, value in vars(module).items() if isinstance(value, Agent)] == []
    assert name not in vars(module)


@pytest.mark.parametrize("role", ROLES)
def test_each_build_returns_its_own_agent(role: PhaseRole) -> None:
    assert BUILDERS[role]() is not BUILDERS[role]()


@pytest.mark.parametrize("role", ROLES)
def test_two_builds_bake_the_same_model(role: PhaseRole) -> None:
    build = BUILDERS[role]
    assert baked_model_id(build()) == baked_model_id(build()) == BAKED_MODELS[role]


@pytest.mark.parametrize("role", ROLES)
def test_the_built_agent_defers_its_model_check(role: PhaseRole) -> None:
    """A resolved model reaches a provider at build time, so the id stays a
    string until the run."""
    assert BUILDERS[role]().model == BAKED_MODELS[role]


@pytest.mark.parametrize("role", ROLES)
def test_two_builds_carry_the_same_tools(role: PhaseRole) -> None:
    build = BUILDERS[role]
    names = agent_tool_names(build())
    assert names == agent_tool_names(build())
    assert names == TOOL_NAMES[role]


@pytest.mark.parametrize("role", ROLES)
def test_the_built_agent_keeps_its_identity(role: PhaseRole) -> None:
    assert BUILDERS[role]().name == role


@pytest.mark.parametrize("role", ROLES)
def test_an_override_on_one_build_cannot_reach_another(role: PhaseRole) -> None:
    """An override is state on one instance, so a second build never sees it."""
    build = BUILDERS[role]
    running = build()
    stub: FunctionToolset[Any] = FunctionToolset(tools=[Tool(stub_tool)])

    with running.override(name="pinned", toolsets=[stub]):
        assert running.name == "pinned"
        assert agent_tool_names(running) == {"stub_tool"}

        fresh = build()
        assert fresh.name == role
        assert agent_tool_names(fresh) == TOOL_NAMES[role]


def test_the_dispatch_map_holds_factories_not_agents() -> None:
    assert set(BUILD_SUB_AGENT_BY_ROLE) == set(ROLES)
    for build in BUILD_SUB_AGENT_BY_ROLE.values():
        assert not isinstance(build, Agent)
        assert isinstance(build(), Agent)


def test_the_model_map_reports_what_each_factory_bakes() -> None:
    assert SUB_AGENT_MODEL_BY_ROLE == BAKED_MODELS


def test_the_registry_agrees_with_the_dispatch_map() -> None:
    """Two places enumerate the phase roles; neither may drift."""
    defaults = phase_defaults()
    assert {role: defaults[role] for role in ROLES} == SUB_AGENT_MODEL_BY_ROLE


STRATEGY_RENDERERS = {
    "base_system_prompt",
    "pinned_frame_workspace",
    "pinned_frame_sheets",
    "pinned_graph_state",
    "pinned_ledger",
    "pinned_discovered_searches",
}

GENERIC_RENDERERS = {
    "pinned_user_memories",
    "pinned_scratchpad",
    "pinned_run_budget",
}

INSTRUCTION_ORDER = {
    "frame": [
        "base_system_prompt",
        "pinned_user_memories",
        "pinned_scratchpad",
        "pinned_frame_workspace",
        "pinned_frame_sheets",
        "pinned_run_budget",
    ],
    "execution": [
        "base_system_prompt",
        "pinned_graph_state",
        "pinned_user_memories",
        "pinned_scratchpad",
        "pinned_ledger",
        "pinned_discovered_searches",
        "pinned_run_budget",
    ],
    "verification": [
        "base_system_prompt",
        "pinned_researcher_request",
        "pinned_graph_state",
        "pinned_user_memories",
        "pinned_scratchpad",
        "pinned_ledger",
        "pinned_discovered_searches",
        "pinned_run_budget",
    ],
}


def _named(module: ModuleType) -> set[str]:
    """The renderers a module defines. A type it declares is not one."""
    return {
        name
        for name, value in vars(module).items()
        if inspect.isfunction(value) and value.__module__ == module.__name__
    }


def test_the_generic_module_renders_no_strategy_content() -> None:
    assert _named(_instructions) == GENERIC_RENDERERS


def test_the_product_module_owns_every_strategy_renderer() -> None:
    assert _named(strategy_instructions) >= STRATEGY_RENDERERS


@pytest.mark.parametrize("role", sorted(BUILDERS))
def test_each_agent_pins_its_renderers_in_the_same_order(role: PhaseRole) -> None:
    names = pinned_instructions(BUILDERS[role]())
    assert names[1:] == INSTRUCTION_ORDER[role]


def test_phase_and_lead_agents_construct_without_pydantic_ai_deprecation() -> None:
    """Building the phase and Lead agents must not trip any pydantic-ai
    deprecation. ``simplefilter("always")`` keeps a warning that fires on an
    earlier build from being swallowed here.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for build in (*BUILDERS.values(), build_lead_agent):
            build()

    offenders = [
        str(w.message)
        for w in caught
        if issubclass(w.category, PydanticAIDeprecationWarning)
    ]
    assert offenders == []
