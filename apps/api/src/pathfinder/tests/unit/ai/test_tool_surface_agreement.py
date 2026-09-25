"""Agreement between the tool names an agent's instructions mention and the
tool names its toolsets register."""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai import Agent

from pathfinder.ai.agents.execution import (
    _EXECUTION_INSTRUCTIONS,
    build_execution_agent,
)
from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS, build_frame_agent
from pathfinder.ai.agents.verification import (
    _VERIFICATION_INSTRUCTIONS,
    build_verification_agent,
)
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.tools.toolsets.verification import build_toolset
from pathfinder.assistants.pathfinder_spec import RESEARCH_TOOL_SOURCE
from pathfinder.tests._support.sub_agents import agent_tool_names, toolset_tool_names

# The served tools, under the prefix the runtime wraps the source in. They are
# reachable only where the deployment admits that server.
_SOURCE_TOOL_NAMES = frozenset(
    f"{RESEARCH_TOOL_SOURCE.name}_{tool}" for tool in RESEARCH_TOOL_SOURCE.tools or ()
)

# Every name a real tool answers to. An instruction may name any of these; a
# token outside this set is prose, not a tool call.
_TOOL_NAME_TOKENS = frozenset(
    {
        # Catalog and framing
        "browse_search_categories",
        "drop_criterion",
        "get_parameter_options",
        "get_record_types",
        "get_search_overview",
        "list_saved_strategies",
        "list_searches",
        "list_transforms",
        "lookup_phyletic_codes",
        "read_experiment",
        "search_example_plans",
        "search_for_searches",
        "set_criterion",
        "set_structure",
        # Strategy build and edit
        "add_step_filter",
        "add_step_report",
        "apply_operations",
        "build_strategy",
        "check_study_step",
        "clear_strategy",
        "create_eda_step",
        "delete_step",
        "describe_eda_study",
        "edit_strategy",
        "open_eda_analysis",
        "preview_eda_subset",
        "run_eda_compute",
        "search_eda_studies",
        "set_eda_filters",
        "insert_saved_strategy",
        "rename_strategy",
        "replace_subtree",
        "update_combine_operator",
        "update_leaf_params",
        "update_step_metadata",
        # Results, controls and gene sets
        "export_gene_set",
        "get_download_url",
        "get_estimated_size",
        "get_sample_records",
        "get_strategy",
        "list_gene_sets",
        "optimize_search_parameters",
        "run_control_tests_on_search",
        "run_control_tests_on_step",
        "save_gene_set",
        # Gene lookup, plus the two tools the research source serves
        "get_ai_expression_summary",
        "lookup_gene_records",
        "research_literature_search",
        "research_web_search",
        "resolve_gene_ids_to_records",
        # Lead orchestration
        "build_control_set",
        "classify_user_intent",
        "compare_search_variants",
        "compare_variants_scored",
        "consult_user",
        "frame_problem",
        "get_live_strategy_state",
        "list_control_sets",
        "read_control_set",
        "read_gene_ids_from_gene_set",
        "read_gene_ids_from_strategy",
        "read_gene_record",
        "read_ledger_section",
        "recover_failed_steps",
        "verify_strategy",
        # Available in every phase
        "remember",
        "request_search_inspection",
        "search_memory",
        "think",
        # Scratchpad
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

# A backticked identifier that a call or a bare mention closes.
_BACKTICKED_NAME = re.compile(r"`{1,2}([a-z_][a-z0-9_]*)\s*(?:\(|`)")


def _instructed_tool_names(instructions: str) -> set[str]:
    """The real tool names an instruction text mentions."""
    return set(_BACKTICKED_NAME.findall(instructions)) & _TOOL_NAME_TOKENS


_SURFACES: dict[str, tuple[Callable[[], Agent[Any, Any]], str]] = {
    "frame": (build_frame_agent, _FRAME_INSTRUCTIONS),
    "execution": (build_execution_agent, _EXECUTION_INSTRUCTIONS),
    "verification": (build_verification_agent, _VERIFICATION_INSTRUCTIONS),
    "lead": (build_lead_agent, LEAD_INSTRUCTIONS),
}


def _all_registered_names() -> set[str]:
    names: set[str] = set()
    for build, _ in _SURFACES.values():
        names |= agent_tool_names(build())
    return names


def test_verify_toolset_contains_instructed_gene_chain() -> None:
    """VERIFY resolves control gene IDs through a chain its toolset registers."""
    names = toolset_tool_names(build_toolset())
    for tool in ("lookup_gene_records", "resolve_gene_ids_to_records"):
        assert tool in names, f"{tool} is instructed by VERIFY but not registered"


def test_the_research_reads_are_served_and_not_registered() -> None:
    """The two research tools reach an agent through the source, not a toolset."""
    assert {
        "research_literature_search",
        "research_web_search",
    } == _SOURCE_TOOL_NAMES
    assert _SOURCE_TOOL_NAMES & _all_registered_names() == set()


@pytest.mark.parametrize("role", ["frame", "execution", "verification", "lead"])
def test_every_instructed_tool_is_callable_by_its_agent(role: str) -> None:
    build, instructions = _SURFACES[role]
    instructed = _instructed_tool_names(instructions)
    # An extraction that finds nothing passes the check below without testing it.
    assert instructed, f"{role} instructions name no known tool; the check is void"
    reachable = agent_tool_names(build()) | _SOURCE_TOOL_NAMES
    missing = sorted(instructed - reachable)
    assert not missing, f"{role} instructions name uncallable tools: {missing}"


def test_tool_name_tokens_are_all_real_tools() -> None:
    """The token list stays honest: no entry names a tool nobody registers."""
    stale = sorted(_TOOL_NAME_TOKENS - _all_registered_names() - _SOURCE_TOOL_NAMES)
    assert not stale, f"token list names unregistered tools: {stale}"


def test_update_search_decision_absent() -> None:
    """The superseded discovery-decision tool no longer exists."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("pathfinder.ai.tools.standalone.catalog_selection")
