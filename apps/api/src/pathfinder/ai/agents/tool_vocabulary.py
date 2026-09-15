"""The PathFinder tool names the runtime's guards key on.

The guards are generic mechanisms: one refuses a repeated read-only call, the
other gives a search-specific hint on a 404. Which tools those are is
PathFinder's vocabulary, and it lives here.
"""

from __future__ import annotations

from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard

__all__ = [
    "DISCOVERY_CALL_CAPS",
    "READ_ONLY_TOOLS",
    "SEARCH_LOOKUP_TOOLS",
    "build_tool_repetition_guard",
]

# Inspectors: the same call with the same arguments returns the same answer,
# so repeating one is not progress. Every name is a tool the Lead or a
# sub-agent carries. Anything absent resets the guard's counter.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        # Catalog and discovery
        "get_record_types",
        "list_searches",
        "search_for_searches",
        "search_example_plans",
        "get_search_overview",
        "get_parameter_options",
        "lookup_phyletic_codes",
        "lookup_gene_records",
        "read_gene_record",
        "get_ai_expression_summary",
        # EDA catalog reads
        "search_eda_studies",
        "describe_eda_study",
        # Strategy inspection
        "get_strategy",
        "get_estimated_size",
        "get_sample_records",
        "get_download_url",
        # Workbench and experiment reads
        "list_workbench_gene_sets",
        "get_evaluation_summary",
        "get_enrichment_results",
        "get_confidence_scores",
        "get_experiment_config",
        "get_result_gene_lists",
        # Research, served by the research tool source
        "research_web_search",
        "research_literature_search",
        # Memory
        "search_memory",
        # Lead reads
        "read_ledger_section",
        "get_live_strategy_state",
        "list_control_sets",
    }
)

# A 404 from one of these means the search name does not exist on the site,
# which needs different advice from a 404 anywhere else.
SEARCH_LOOKUP_TOOLS: frozenset[str] = frozenset(
    {
        "get_search_overview",
        "get_parameter_options",
    }
)


# A catalog tool answers from a fixed catalog, so a run that keeps rephrasing
# its query reads the same source again. A research tool reads a different
# slice of an open corpus with every phrasing, so its cap bounds the spend of
# one run and nothing else. Each cap is the run's budget for one tool, whatever
# the arguments.
DISCOVERY_CALL_CAPS: dict[str, int] = {
    "search_eda_studies": 6,
    "research_web_search": 12,
    "research_literature_search": 12,
    "search_for_searches": 12,
}


def build_tool_repetition_guard() -> ToolRepetitionGuard:
    """A repetition guard that watches PathFinder's read-only tools."""
    return ToolRepetitionGuard(
        read_only_tools=READ_ONLY_TOOLS,
        call_caps=DISCOVERY_CALL_CAPS,
    )
