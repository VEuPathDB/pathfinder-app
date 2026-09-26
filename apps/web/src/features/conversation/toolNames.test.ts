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
  "delete_note",
  "delete_step",
  "describe_eda_study",
  "describe_site",
  "drop_criterion",
  "edit_strategy",
  "export_gene_set",
  "frame_problem",
  "get_ai_expression_summary",
  "get_download_url",
  "get_estimated_size",
  "get_live_strategy_state",
  "get_parameter_options",
  "get_record_types",
  "get_sample_records",
  "get_search_overview",
  "get_strategy",
  "insert_saved_strategy",
  "list_control_sets",
  "list_notes",
  "list_saved_strategies",
  "list_searches",
  "list_transforms",
  "list_veupathdb_sites",
  "list_gene_sets",
  "lookup_gene_records",
  "lookup_phyletic_codes",
  "note",
  "open_eda_analysis",
  "optimize_search_parameters",
  "pin_note",
  "preview_eda_subset",
  "promote_to_memory",
  "propose_changes",
  "read_control_set",
  "read_gene_ids_from_gene_set",
  "read_experiment",
  "read_gene_ids_from_strategy",
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
  "save_gene_set",
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
  "research_literature_search",
  "research_web_search",
  "separate_controls",
  "adopt_separating_strategy",
  // The site help assistant's wdk tool source, which prefixes its tools with
  // the source name (`assistants/site_help/spec.py::WDK_TOOL_SOURCE`).
  "wdk_list_record_types",
  "wdk_search_for_searches",
  "wdk_run_control_tests_on_search",
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
    expect(humanizeToolName("consult_user")).toBe("Ask you");
  });

  it("names the two gene-set tools by what they do", () => {
    expect(humanizeToolName("save_gene_set")).toBe("Save gene set");
    expect(humanizeToolName("list_gene_sets")).toBe("List gene sets");
  });

  it("names the two control reads by what they return", () => {
    expect(humanizeToolName("read_gene_ids_from_gene_set")).toBe(
      "Gene ids from gene set",
    );
    expect(humanizeToolName("read_gene_ids_from_strategy")).toBe(
      "Gene ids from strategy",
    );
  });

  it("labels the site help assistant's wdk tools like their own tools", () => {
    expect(
      [
        "wdk_list_record_types",
        "wdk_search_for_searches",
        "wdk_run_control_tests_on_search",
      ].map(humanizeToolName),
    ).toEqual(["List record types", "Find searches", "Run control tests"]);
  });

  it("names the rename by what it does", () => {
    expect(humanizeToolName("rename_strategy")).toBe("Rename strategy");
  });

  it("says an experiment it reads belongs to another site", () => {
    expect(humanizeToolName("read_experiment")).toBe("Read another site's experiment");
  });

  it("never falls back for a name the backend registers", () => {
    const unmapped = REGISTERED.filter((name) => TOOL_LABELS[name] === undefined);
    expect(unmapped).toEqual([]);
  });

  it("labels no name the backend does not register", () => {
    const stale = Object.keys(TOOL_LABELS).filter((name) => !REGISTERED.includes(name));
    expect(stale).toEqual([]);
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
      "Clear the strategy? This removes every step from this conversation and from VEuPathDB.",
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

  it("asks for the site help control tests in the label's words", () => {
    expect(approvalPromptFor("wdk_run_control_tests_on_search")).toBe(
      "Run control tests needs your approval before it runs.",
    );
  });

  it("asks for a separation run by naming what it measures and how long", () => {
    expect(approvalPromptFor("separate_controls")).toBe(
      "Run the separation? It measures candidate searches against your controls " +
        "on the site and takes about five minutes.",
    );
  });

  it("asks a removal in the words the api wrote from the live strategy", () => {
    const asked =
      "Replace step 'Transform by Orthology' (GenesByOrthologs, 142 genes) and the steps under it?";
    expect(approvalPromptFor("replace_subtree", asked)).toBe(asked);
    expect(
      approvalPromptFor("delete_step", "Delete step 'Intersect' (116 genes)?"),
    ).toBe("Delete step 'Intersect' (116 genes)?");
    expect(approvalPromptFor("replace_subtree")).toBe(
      "Replace part of a strategy needs your approval before it runs.",
    );
  });

  it("names no internal word in any bespoke prompt", () => {
    for (const prompt of Object.values(TOOL_APPROVAL_PROMPTS)) {
      expect(INTERNAL.test(prompt), prompt).toBe(false);
    }
  });
});
