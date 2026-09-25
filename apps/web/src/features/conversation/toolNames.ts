export const TOOL_LABELS: Record<string, string> = {
  // Orchestration and inspection
  read_ledger_section: "Read progress",
  classify_user_intent: "Read the request",
  consult_user: "Ask you",
  propose_changes: "Propose changes",
  recover_failed_steps: "Repair steps",
  think: "Think",
  // Planning
  frame_problem: "Plan the searches",
  search_for_searches: "Find searches",
  get_search_overview: "Read a search",
  request_search_inspection: "Read a search",
  set_criterion: "Choose a search",
  set_structure: "Arrange the steps",
  drop_criterion: "Drop a search",
  list_saved_strategies: "List saved strategies",
  // Catalog
  browse_search_categories: "Browse search categories",
  list_searches: "List searches",
  list_transforms: "List transforms",
  get_record_types: "List record types",
  get_parameter_options: "Read parameter options",
  lookup_phyletic_codes: "Look up phyletic codes",
  search_example_plans: "Find example plans",
  read_experiment: "Read another site's experiment",
  describe_site: "Describe site",
  list_veupathdb_sites: "List VEuPathDB sites",
  // Studies
  search_eda_studies: "Find studies",
  describe_eda_study: "Read study",
  open_eda_analysis: "Open study",
  set_eda_filters: "Filter samples",
  preview_eda_subset: "Preview samples",
  run_eda_compute: "Run differential expression",
  create_eda_step: "Add study step",
  // Comparisons and controls
  compare_search_variants: "Compare variants",
  compare_variants_scored: "Score variants",
  build_control_set: "Build control set",
  list_control_sets: "List control sets",
  read_control_set: "Read control set",
  read_gene_ids_from_gene_set: "Gene ids from gene set",
  read_gene_ids_from_strategy: "Gene ids from strategy",
  separate_controls: "Separate the controls",
  adopt_separating_strategy: "Build the measured strategy",
  // Strategy
  build_strategy: "Build the strategy",
  verify_strategy: "Check the strategy",
  edit_strategy: "Edit the strategy",
  get_strategy: "Read the strategy",
  get_live_strategy_state: "Read the strategy",
  apply_operations: "Update strategy",
  clear_strategy: "Clear strategy",
  rename_strategy: "Rename strategy",
  delete_step: "Delete step",
  insert_saved_strategy: "Insert saved strategy",
  add_step_filter: "Add filter step",
  add_step_report: "Add report step",
  update_combine_operator: "Change how steps combine",
  update_leaf_params: "Update parameters",
  update_step_metadata: "Rename step",
  replace_subtree: "Replace part of a strategy",
  get_estimated_size: "Count results",
  // Results and gene sets
  get_sample_records: "Read sample records",
  get_download_url: "Prepare download",
  save_gene_set: "Save gene set",
  list_gene_sets: "List gene sets",
  export_gene_set: "Export gene set",
  lookup_gene_records: "Look up genes",
  get_ai_expression_summary: "Read expression summary",
  resolve_gene_ids_to_records: "Resolve gene ids",
  // Verification and durable jobs
  run_control_tests_on_search: "Run control tests",
  check_study_step: "Check the study step",
  run_control_tests_on_step: "Run control tests",
  optimize_search_parameters: "Optimize parameters",
  // Scratchpad and memory
  note: "Save note",
  read_note: "Read note",
  update_note: "Update note",
  delete_note: "Delete note",
  pin_note: "Pin note",
  unpin_note: "Unpin note",
  search_notes: "Search notes",
  list_notes: "List notes",
  promote_to_memory: "Save to memory",
  search_memory: "Search memory",
  remember: "Remember",
  // Research, served by the research tool source
  research_web_search: "Web search",
  research_literature_search: "Literature search",
  // Site help, served by the wdk tool source
  wdk_list_record_types: "List record types",
  wdk_search_for_searches: "Find searches",
  wdk_run_control_tests_on_search: "Run control tests",
};

/**
 * Render-ready label for a tool name shown anywhere in the UI (tool cards,
 * trace rows, task cards, approval prompts). Every registered tool is listed
 * above; the Title-case fallback covers a name only this build has retired.
 */
export function humanizeToolName(name: string): string {
  const known = TOOL_LABELS[name];
  if (known !== undefined) return known;
  const spaced = name.replace(/^tool-/, "").replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * The whole sentence an approval card asks. A call that destroys work names
 * what it destroys; everything else reads as the standing sentence.
 */
export const TOOL_APPROVAL_PROMPTS: Record<string, string> = {
  clear_strategy:
    "Clear the strategy? This removes every step from this conversation and from VEuPathDB.",
  separate_controls:
    "Run the separation? It measures candidate searches against your controls " +
    "on the site and takes about five minutes.",
};

/**
 * The approvals whose question the api writes when it asks, from the live
 * strategy, as the call's first summary line.
 */
const ASKED_BY_THE_API: ReadonlySet<string> = new Set([
  "delete_step",
  "replace_subtree",
]);

/** The line that names what one call acts on, when the api wrote one for it. */
export function approvalSubjectFor(name: string, asked: string | null): string | null {
  return ASKED_BY_THE_API.has(name) ? asked : null;
}

/** The approval question for one tool call, ready to render. */
export function approvalPromptFor(name: string, asked: string | null = null): string {
  const subject = approvalSubjectFor(name, asked);
  if (subject !== null) return subject;
  const bespoke = TOOL_APPROVAL_PROMPTS[name];
  if (bespoke !== undefined) return bespoke;
  return `${humanizeToolName(name)} needs your approval before it runs.`;
}
