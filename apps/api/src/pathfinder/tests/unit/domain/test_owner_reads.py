from __future__ import annotations

from pathfinder.domain.owner_reads import (
    NOT_SHARED,
    OWNER_READ_TOOLS,
    without_owner_reads,
)
from pathfinder.tests._support.offered_tools import offered_tool_names


def _call(call_id: str, tool: str, output: object) -> list[dict[str, object]]:
    return [
        {"type": "tool-input-start", "toolCallId": call_id, "toolName": tool},
        {
            "type": "tool-input-available",
            "toolCallId": call_id,
            "toolName": tool,
            "input": {},
        },
        {"type": "tool-output-available", "toolCallId": call_id, "output": output},
    ]


THREAD_TOOLS = frozenset(
    {
        "add_step_filter",
        "adopt_separating_strategy",
        "apply_operations",
        "ask_to_read_the_account",
        "browse_search_categories",
        "build_control_set",
        "build_phyletic_expression",
        "build_strategy",
        "clear_strategy",
        "compare_search_variants",
        "compare_variants_scored",
        "consult_user",
        "count_by_column",
        "count_search",
        "count_step_by_column",
        "create_eda_step",
        "delete_note",
        "delete_step",
        "describe_eda_study",
        "drop_criterion",
        "edit_strategy",
        "export_gene_set",
        "frame_problem",
        "genes_in_search",
        "get_ai_expression_summary",
        "get_estimated_size",
        "get_live_strategy_state",
        "get_parameter_options",
        "get_record_types",
        "get_sample_records",
        "get_search_overview",
        "get_strategy",
        "insert_saved_strategy",
        "investigate_gene_models",
        "list_notes",
        "list_searches",
        "list_transforms",
        "lookup_gene_records",
        "lookup_phyletic_codes",
        "note",
        "open_eda_analysis",
        "optimize_search_parameters",
        "pin_note",
        "plan_gene_model_audit",
        "preview_eda_subset",
        "promote_to_memory",
        "propose_changes",
        "propose_readings",
        "read_eda_statistics",
        "read_experiment",
        "read_gene_ids_from_strategy",
        "read_gene_record",
        "read_ledger_section",
        "read_note",
        "read_step_ids",
        "recover_failed_steps",
        "remember",
        "rename_strategy",
        "replace_subtree",
        "request_search_inspection",
        "research_literature_search",
        "research_web_search",
        "resolve_gene_ids_to_records",
        "run_control_tests_on_search",
        "run_control_tests_on_step",
        "run_eda_compute",
        "run_eda_dimensionality_reduction",
        "save_gene_set",
        "search_eda_studies",
        "search_example_plans",
        "search_for_searches",
        "search_notes",
        "separate_controls",
        "set_criterion",
        "set_eda_filters",
        "set_structure",
        "start_gene_model_audit",
        "step_columns",
        "think",
        "unpin_note",
        "update_combine_operator",
        "update_leaf_params",
        "update_note",
        "update_step_metadata",
        "verify_strategy",
    }
)


def test_every_tool_an_agent_carries_is_classed_as_an_owner_read_or_not() -> None:
    offered = offered_tool_names()

    assert offered - OWNER_READ_TOOLS - THREAD_TOOLS == set()
    assert offered >= OWNER_READ_TOOLS
    assert OWNER_READ_TOOLS.isdisjoint(THREAD_TOOLS)


def test_recalled_memories_are_not_shown() -> None:
    chunks: list[dict[str, object]] = [
        {
            "type": "data-memory-retrieved",
            "data": {"memories": [{"key": "m1", "name": "Prefers 3D7"}]},
        }
    ]

    assert without_owner_reads(chunks) == [
        {"type": "data-memory-retrieved", "data": {"memories": []}}
    ]


def test_an_owner_read_keeps_its_call_and_loses_its_output() -> None:
    chunks = _call("c-1", "list_my_threads", {"threads": ["Malaria antigens"]})

    shown = without_owner_reads(chunks)

    assert shown[:2] == chunks[:2]
    assert shown[2] == {
        "type": "tool-output-available",
        "toolCallId": "c-1",
        "output": NOT_SHARED,
    }


def test_another_tool_keeps_its_output() -> None:
    chunks = _call("c-2", "search_catalog", {"searches": ["GenesByText"]})

    assert without_owner_reads(chunks) == chunks


def test_a_failed_owner_read_loses_its_error_text() -> None:
    chunks: list[dict[str, object]] = [
        *_call("c-3", "read_my_thread", None)[:2],
        {
            "type": "tool-output-error",
            "toolCallId": "c-3",
            "errorText": "thread Malaria antigens not found",
        },
    ]

    assert without_owner_reads(chunks)[2] == {
        "type": "tool-output-error",
        "toolCallId": "c-3",
        "errorText": NOT_SHARED,
    }


def test_an_owner_read_loses_its_input() -> None:
    chunks: list[dict[str, object]] = [
        {
            "type": "tool-input-start",
            "toolCallId": "c-4",
            "toolName": "read_control_set",
        },
        {
            "type": "tool-input-delta",
            "toolCallId": "c-4",
            "inputTextDelta": '{"name": "',
        },
        {
            "type": "tool-input-available",
            "toolCallId": "c-4",
            "toolName": "read_control_set",
            "input": {"name": "Gametocyte markers"},
        },
    ]

    shown = without_owner_reads(chunks)

    assert shown[1]["inputTextDelta"] == ""
    assert shown[2]["input"] == {}
    assert "Gametocyte markers" not in str(shown)
