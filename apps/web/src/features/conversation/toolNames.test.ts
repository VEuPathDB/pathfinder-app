import { describe, expect, it } from "vitest";

import {
  TOOL_APPROVAL_PROMPTS,
  TOOL_LABELS,
  approvalPromptFor,
  humanizeToolName,
} from "./toolNames";

const INTERNAL = /\b(EDA|WDK|FRAME|BUILD|VERIFY|Frame|Ledger|Lead|sub-agent)\b/;

/**
 * Every tool an agent of this application can call. Taken from the backend
 * registry the api suite enumerates in
 * `apps/api/src/pathfinder/tests/unit/ai/tools/test_tool_summaries.py::_registered`.
 */
const REGISTERED = [
  "add_step_analysis",
  "add_step_filter",
  "add_step_report",
  "apply_operations",
  "browse_search_categories",
  "build_control_set",
  "build_strategy",
  "classify_user_intent",
  "clear_strategy",
  "compare_search_variants",
  "compare_variants_scored",
  "consult_user",
  "create_eda_step",
  "create_workbench_gene_set",
  "delete_note",
  "delete_step",
  "describe_eda_study",
  "describe_site",
  "drop_criterion",
  "edit_strategy",
  "export_gene_set",
  "frame_problem",
  "get_confidence_scores",
  "get_download_url",
  "get_enrichment_results",
  "get_ensemble_analysis",
  "get_estimated_size",
  "get_evaluation_summary",
  "get_experiment_config",
  "get_live_strategy_state",
  "get_parameter_options",
  "get_record_types",
  "get_result_gene_lists",
  "get_sample_records",
  "get_search_overview",
  "get_step_contributions",
  "get_strategy",
  "import_control_ids_from_gene_set",
  "import_control_ids_from_strategy",
  "insert_saved_strategy",
  "list_control_sets",
  "list_notes",
  "list_searches",
  "list_transforms",
  "list_veupathdb_sites",
  "list_workbench_gene_sets",
  "literature_search",
  "lookup_gene_records",
  "lookup_phyletic_codes",
  "note",
  "open_eda_analysis",
  "optimize_search_parameters",
  "pin_note",
  "preview_eda_subset",
  "promote_to_memory",
  "read_ledger_section",
  "read_note",
  "recover_failed_steps",
  "remember",
  "rename_strategy",
  "replace_subtree",
  "request_search_inspection",
  "resolve_gene_ids_to_records",
  "run_control_tests_on_search",
  "check_study_step",
  "run_control_tests_on_step",
  "run_eda_compute",
  "run_gene_set_enrichment",
  "search_eda_studies",
  "search_example_plans",
  "search_for_searches",
  "search_memory",
  "search_notes",
  "set_criterion",
  "set_eda_filters",
  "set_structure",
  "think",
  "unpin_note",
  "update_combine_operator",
  "update_leaf_params",
  "update_note",
  "update_step_metadata",
  "verify_strategy",
  "web_search",
];

describe("humanizeToolName", () => {
  it("maps the study tools to the verbs the glossary names", () => {
    expect(humanizeToolName("search_eda_studies")).toBe("Find studies");
    expect(humanizeToolName("describe_eda_study")).toBe("Read study");
    expect(humanizeToolName("open_eda_analysis")).toBe("Open study");
    expect(humanizeToolName("set_eda_filters")).toBe("Filter samples");
    expect(humanizeToolName("preview_eda_subset")).toBe("Preview samples");
    expect(humanizeToolName("run_eda_compute")).toBe("Run differential expression");
    expect(humanizeToolName("create_eda_step")).toBe("Add study step");
  });

  it("maps the phase tools without naming a phase", () => {
    expect(humanizeToolName("frame_problem")).toBe("Plan the searches");
    expect(humanizeToolName("build_strategy")).toBe("Build the strategy");
    expect(humanizeToolName("verify_strategy")).toBe("Check the strategy");
    expect(humanizeToolName("recover_failed_steps")).toBe("Repair steps");
    expect(humanizeToolName("read_ledger_section")).toBe("Read progress");
    expect(humanizeToolName("set_criterion")).toBe("Choose a search");
    expect(humanizeToolName("run_control_tests_on_step")).toBe("Run control tests");
    expect(humanizeToolName("consult_user")).toBe("Ask the user");
  });

  it("names the enrichment job by the tool name its task puts on the wire", () => {
    expect(humanizeToolName("geneset_enrichment")).toBe("Gene set enrichment");
    expect(humanizeToolName("run_gene_set_enrichment")).toBe("Gene-set enrichment");
  });

  it("never falls back for a name the backend registers", () => {
    const unmapped = REGISTERED.filter((name) => TOOL_LABELS[name] === undefined);
    expect(unmapped).toEqual([]);
  });

  it("lists no label that names an internal word", () => {
    for (const label of Object.values(TOOL_LABELS)) {
      expect(INTERNAL.test(label), label).toBe(false);
    }
  });

  it("title-cases the deleted present_decision tool (no longer mapped)", () => {
    expect(humanizeToolName("present_decision")).toBe("Present decision");
  });

  it("title-cases unknown snake_case names", () => {
    expect(humanizeToolName("some_new_tool")).toBe("Some new tool");
  });

  it("strips a leading tool- prefix", () => {
    expect(humanizeToolName("tool-some_new_tool")).toBe("Some new tool");
  });
});

describe("approvalPromptFor", () => {
  it("asks about a deletion by naming what the deletion removes", () => {
    expect(approvalPromptFor("clear_strategy")).toBe(
      "Clear the strategy? This removes every step from this thread and from VEuPathDB.",
    );
  });

  it("falls back to the label plus the standing sentence", () => {
    expect(approvalPromptFor("optimize_search_parameters")).toBe(
      "Optimize parameters needs your approval before it runs.",
    );
    expect(approvalPromptFor("some_new_tool")).toBe(
      "Some new tool needs your approval before it runs.",
    );
  });

  it("names no internal word in any bespoke prompt", () => {
    for (const prompt of Object.values(TOOL_APPROVAL_PROMPTS)) {
      expect(INTERNAL.test(prompt), prompt).toBe(false);
    }
  });
});
