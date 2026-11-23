from __future__ import annotations

import json

import pytest

from strategist.domain.owner_reads import (
    NOT_SHARED,
    OWNER_READ_TOOLS,
    UPLOAD_BLOCK,
    without_owner_reads,
)
from strategist.tests._support.tool_names import all_tool_names


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
        "ask_eda_cut",
        "ask_to_read_the_account",
        "audit_gene_evidence",
        "audit_gene_length",
        "audit_gene_split",
        "audit_genome_provenance",
        "audit_intron_support",
        "audit_pseudogene_anatomy",
        "audit_pseudogene_call",
        "audit_selenoprotein_end",
        "audit_strain_model",
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
        "list_notes",
        "list_record_columns",
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
        "rate_with_interval",
        "read_eda_statistics",
        "read_experiment",
        "read_gene_ids_from_strategy",
        "read_gene_record",
        "read_ledger_section",
        "read_note",
        "read_search_table",
        "read_step_ids",
        "record_gene_model_verdicts",
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
    offered = all_tool_names()

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


def test_an_owner_read_keeps_only_what_names_the_call() -> None:
    chunks: list[dict[str, object]] = [
        {"type": "tool-input-start", "toolCallId": "c-5", "toolName": "list_gene_sets"},
        {
            "type": "tool-input-error",
            "toolCallId": "c-5",
            "toolName": "list_gene_sets",
            "input": {"site": "plasmodb", "owner": "Gametocyte sets"},
            "errorText": "Gametocyte sets is not a site",
            "providerMetadata": {"note": "Gametocyte sets"},
        },
    ]

    assert without_owner_reads(chunks)[1] == {
        "type": "tool-input-error",
        "toolCallId": "c-5",
        "toolName": "list_gene_sets",
        "input": {},
        "errorText": NOT_SHARED,
    }


UPLOAD = "EDAUD_sF88g1cwo00gw"


def _upload_thread() -> list[dict[str, object]]:
    state = {
        "siteId": "plasmodb",
        "datasetId": UPLOAD,
        "studyId": "STUDY_up_3d7",
        "analysisId": "a-up-1",
        "revision": 1,
        "studyDisplayName": "My 3D7 RNA-seq upload",
        "displayName": "gametocyte subset",
        "numFilters": 0,
        "numComputations": 0,
        "filters": [],
        "filterSummaries": [],
        "entityCounts": [],
        "canExportRows": True,
    }
    return [
        {
            "type": "tool-input-start",
            "toolCallId": "c-9",
            "toolName": "open_eda_analysis",
        },
        {
            "type": "tool-input-available",
            "toolCallId": "c-9",
            "toolName": "open_eda_analysis",
            "input": {"datasetId": UPLOAD, "purpose": "gametocyte subset"},
        },
        {
            "type": "tool-output-available",
            "toolCallId": "c-9",
            "output": {
                "datasetId": UPLOAD,
                "studyDisplayName": "My 3D7 RNA-seq upload",
            },
        },
        {"type": "data-eda.analysis-state", "id": "a-up-1", "data": state},
        *_call("c-10", "preview_eda_subset", {"analysisId": "a-up-1", "count": 812}),
        {"type": "text-delta", "id": "t-1", "delta": f"I opened {UPLOAD} for you."},
    ]


def test_a_read_of_the_owners_upload_is_not_shown() -> None:
    shown = json.dumps(without_owner_reads(_upload_thread()))

    assert [UPLOAD in shown, "My 3D7 RNA-seq upload" in shown, "812" in shown] == [
        False,
        False,
        False,
    ]


def test_a_read_of_a_curated_study_is_shown() -> None:
    chunks = _call("c-11", "open_eda_analysis", {"datasetId": "DS_53f554ec6a"})

    assert without_owner_reads(chunks) == chunks


def test_a_name_split_across_deltas_is_not_shown() -> None:
    chunks: list[dict[str, object]] = [
        *_upload_thread()[:4],
        {"type": "reasoning-delta", "id": "r-1", "delta": "The My 3D7 RNA"},
        {"type": "reasoning-delta", "id": "r-1", "delta": "-seq upload holds it."},
        {"type": "text-delta", "id": "t-2", "delta": "Kinases on "},
        {"type": "text-delta", "id": "t-2", "delta": "chromosome 3."},
    ]

    shown = without_owner_reads(chunks)

    assert [c["delta"] for c in shown if c["type"].endswith("-delta")] == [
        UPLOAD_BLOCK,
        "",
        "Kinases on ",
        "chromosome 3.",
    ]
    assert "RNA-seq upload" not in json.dumps(shown)


def test_a_chunk_of_another_shape_that_names_an_upload_is_withheld() -> None:
    chunks: list[dict[str, object]] = [
        {"type": "source-document", "sourceId": "s-1", "title": f"Study {UPLOAD}"},
        {"type": "data-eda.viz", "id": "v-1", "data": {"datasetId": UPLOAD}},
        {"type": "source-document", "sourceId": "s-2", "title": "PlasmoDB release 68"},
    ]

    shown = without_owner_reads(chunks)

    assert shown == [
        {
            "type": "source-document",
            "sourceId": "s-1",
            "title": "Study a private dataset",
        },
        {"type": "source-document", "sourceId": "s-2", "title": "PlasmoDB release 68"},
    ]


def _strings(value: object) -> list[str]:
    match value:
        case str():
            return [value]
        case list():
            return [s for item in value for s in _strings(item)]
        case dict():
            return [s for k, v in value.items() for s in [str(k), *_strings(v)]]
        case _:
            return []


@pytest.mark.parametrize(
    "name",
    [
        f"{chr(0xC9)}tude de P. vivax {chr(0x2013)} sang",
        'The "3D7" upload',
        "Gametocytes\nday 12",
    ],
)
def test_a_name_that_json_escapes_is_still_hidden(name: str) -> None:
    chunks: list[dict[str, object]] = [
        {
            "type": "data-eda.analysis-state",
            "id": "a-up-2",
            "data": {
                "datasetId": UPLOAD,
                "analysisId": "a-up-2",
                "studyDisplayName": name,
            },
        },
        {"type": "source-document", "sourceId": "s-1", "title": f"From {name}"},
        {"type": "text-delta", "id": "t-3", "delta": f"Read {name} today."},
    ]

    shown = without_owner_reads(chunks)

    assert [s for s in _strings(shown) if name in s] == []


def test_a_name_reached_through_another_mark_is_hidden() -> None:
    chunks: list[dict[str, object]] = [
        *_call("c-12", "describe_eda_study", {"datasetId": UPLOAD, "studyId": "ST_up"}),
        {
            "type": "data-eda.viz",
            "id": "v-2",
            "data": {"studyId": "ST_up", "displayName": "Ring stage counts"},
        },
        {"type": "source-document", "sourceId": "s-3", "title": "Ring stage counts"},
    ]

    shown = without_owner_reads(chunks)

    assert [
        s for s in _strings(shown) if "Ring stage counts" in s or "ST_up" in s
    ] == []
