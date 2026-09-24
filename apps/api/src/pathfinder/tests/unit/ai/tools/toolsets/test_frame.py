"""The FRAME toolset: which tools it mounts, and how it narrows the enums."""

from __future__ import annotations

import pytest
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder.ai.agents.state import AgentToolState, SearchOverview
from pathfinder.ai.graph.runtime import AgentDeps, ServiceOutageMemory
from pathfinder.ai.tools.toolsets._dynamic import EnumOverrides, ValidatingEnumToolset
from pathfinder.ai.tools.toolsets.frame import _frame_enum_overrides, build_toolset
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

# name -> (every argument, the required ones)
_MOUNTED: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "browse_search_categories": (frozenset({"record_type"}), frozenset()),
    "drop_criterion": (
        frozenset({"criterion_id", "reason"}),
        frozenset({"criterion_id", "reason"}),
    ),
    "get_parameter_options": (
        frozenset(
            {"context_values", "parameter_id", "query", "record_type", "search_name"}
        ),
        frozenset({"parameter_id", "search_name"}),
    ),
    "get_ai_expression_summary": (frozenset({"gene_id"}), frozenset({"gene_id"})),
    "get_record_types": (frozenset(), frozenset()),
    "get_search_overview": (
        frozenset({"record_type", "search_name"}),
        frozenset({"search_name"}),
    ),
    "get_strategy": (frozenset({"graph_id", "summary_only"}), frozenset()),
    "list_saved_strategies": (frozenset(), frozenset()),
    "list_searches": (frozenset({"record_type"}), frozenset()),
    "list_transforms": (frozenset({"record_type"}), frozenset()),
    "lookup_gene_records": (
        frozenset({"limit", "organism", "query"}),
        frozenset({"query"}),
    ),
    "lookup_phyletic_codes": (
        frozenset({"query", "record_type"}),
        frozenset({"query"}),
    ),
    "remember": (
        frozenset({"content", "kind", "name", "summary", "tags"}),
        frozenset({"content", "kind", "name", "summary"}),
    ),
    "search_example_plans": (frozenset({"limit", "query"}), frozenset({"query"})),
    "search_for_searches": (
        frozenset({"category", "keywords", "limit", "query", "record_type"}),
        frozenset({"query"}),
    ),
    "search_memory": (frozenset({"kind", "query", "top_k"}), frozenset({"query"})),
    "set_criterion": (
        frozenset(
            {
                "assumed",
                "criterion_id",
                "params",
                "role",
                "saved_strategy",
                "search_name",
                "text",
                "why",
            }
        ),
        frozenset({"criterion_id", "text"}),
    ),
    "set_structure": (frozenset(), frozenset()),
    "think": (frozenset({"thought"}), frozenset({"thought"})),
}


async def _mounted_tools() -> dict[str, ToolsetTool[AgentDeps]]:
    return await build_toolset().get_tools(agent_run_context())


def _shape(tool: ToolsetTool[AgentDeps]) -> tuple[frozenset[str], frozenset[str]]:
    schema = tool.tool_def.parameters_json_schema
    return (
        frozenset(schema.get("properties", {})),
        frozenset(schema.get("required", [])),
    )


@pytest.mark.asyncio
async def test_the_toolset_mounts_exactly_the_declared_tools() -> None:
    assert set(await _mounted_tools()) == set(_MOUNTED)


@pytest.mark.asyncio
async def test_every_mounted_tool_declares_the_arguments_it_is_called_with() -> None:
    tools = await _mounted_tools()
    assert {name: _shape(tool) for name, tool in tools.items()} == _MOUNTED


@pytest.mark.asyncio
async def test_set_structure_takes_the_structure_node_itself() -> None:
    # The whole tree is one argument, so its schema is the node's own.
    tools = await _mounted_tools()
    schema = tools["set_structure"].tool_def.parameters_json_schema
    assert schema["$ref"] == "#/$defs/StructureNode"


def test_the_toolset_guards_its_enums_at_call_time() -> None:
    toolset = build_toolset()
    assert isinstance(toolset, ValidatingEnumToolset)
    assert isinstance(toolset.wrapped, FunctionToolset)
    assert set(toolset.wrapped.tools) == set(_MOUNTED)


_ENUM_KEYS = (
    ("get_search_overview", "search_name"),
    ("set_criterion", "search_name"),
    ("get_parameter_options", "search_name"),
)

UP = "GenesByRNASeqaaegLVP_AGWG_SRP047470_ebi_rnaSeq_RSRCDESeq"
DOWN = "GenesByRNASeqaaegLVP_AGWG_Houri_aegypti_2023_ebi_rnaSeq_RSRCDESeq"
DOWN_SIBLING = "GenesByRNASeqaaegLVP_AGWG_Houri_aegypti_2023_ebi_rnaSeq_RSRCPercentile"


def _inspected(name: str) -> SearchOverview:
    return SearchOverview(
        search_name=name,
        display_name=name,
        record_type="transcript",
        description="",
        parameter_names=[],
        required_params=[],
    )


def _overrides(
    candidates: list[str],
    outage: ServiceOutageMemory | None = None,
    *,
    discovered: list[str] | None = None,
) -> EnumOverrides:
    state = AgentToolState()
    state.record_catalog_read(listing(candidates))
    for name in discovered or []:
        state.discovered_searches[name] = _inspected(name)
    ctx = agent_run_context(agent_state=state)
    ctx.deps.service_outage = outage or ServiceOutageMemory()
    return _frame_enum_overrides(ctx)


def _give_up_on(outage: ServiceOutageMemory, search: str) -> None:
    """Record enough failures that the resilience layer abandons the search."""
    outage.record_search_failure(search)
    outage.record_search_failure(search)


def test_a_candidate_search_reaches_every_guarded_enum() -> None:
    overrides = _overrides(["GenesByOrthologs"])
    for key in _ENUM_KEYS:
        assert overrides[key] == ["GenesByOrthologs"]


def test_a_discovered_search_is_offered_beside_the_candidates() -> None:
    overrides = _overrides([UP], discovered=[DOWN])
    assert overrides[_ENUM_KEYS[0]] == sorted([UP, DOWN])


def test_a_search_given_up_on_is_no_longer_offered() -> None:
    outage = ServiceOutageMemory()
    _give_up_on(outage, DOWN)
    overrides = _overrides([UP, DOWN], outage)
    for key in _ENUM_KEYS:
        assert overrides[key] == [UP], f"{key} still offered the dead search"


def test_every_outaged_sibling_is_dropped_together() -> None:
    outage = ServiceOutageMemory()
    _give_up_on(outage, DOWN)
    _give_up_on(outage, DOWN_SIBLING)
    overrides = _overrides([UP, DOWN, DOWN_SIBLING], outage)
    assert overrides[_ENUM_KEYS[0]] == [UP]


def test_a_single_failure_is_not_enough_to_evict() -> None:
    """One 5xx may be a blip; the resilience layer retries before giving up, so
    the enum must not drop a search the model is still allowed to retry."""
    outage = ServiceOutageMemory()
    outage.record_search_failure(DOWN)
    overrides = _overrides([UP, DOWN], outage)
    assert sorted(overrides[_ENUM_KEYS[0]]) == sorted([UP, DOWN])


def test_healthy_searches_are_untouched() -> None:
    overrides = _overrides([UP, DOWN])
    assert sorted(overrides[_ENUM_KEYS[0]]) == sorted([UP, DOWN])


def test_no_enum_is_imposed_when_every_candidate_is_down() -> None:
    """Handing the model an empty enum would make every call invalid and it
    could not route around the outage at all."""
    outage = ServiceOutageMemory()
    _give_up_on(outage, DOWN)
    _give_up_on(outage, DOWN_SIBLING)
    assert _overrides([DOWN, DOWN_SIBLING], outage) == {}


def test_outage_memory_counts_per_search_not_per_tool() -> None:
    """The search is down regardless of which tool touched it, so a failure via
    ``get_search_overview`` and one via ``set_criterion`` must add up."""
    outage = ServiceOutageMemory()
    assert outage.record_search_failure(DOWN) == 1
    assert outage.record_search_failure(DOWN) == 2
    assert DOWN in outage.unavailable_searches()
    assert UP not in outage.unavailable_searches()
