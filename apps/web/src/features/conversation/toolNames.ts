export const TOOL_LABELS: Record<string, string> = {
  // Orchestration and inspection
  read_ledger_section: "Read progress",
  classify_user_intent: "Read the request",
  consult_user: "Ask the user",
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
  // Experiments and controls
  compare_search_variants: "Compare variants",
  compare_variants_scored: "Score variants",
  build_control_set: "Build control set",
  list_control_sets: "List control sets",
  import_control_ids_from_gene_set: "Controls from gene set",
  import_control_ids_from_strategy: "Controls from strategy",
  get_experiment_config: "Read experiment setup",
  get_evaluation_summary: "Read evaluation summary",
  get_ensemble_analysis: "Read ensemble analysis",
  get_confidence_scores: "Read confidence scores",
  get_step_contributions: "Compare step contributions",
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
  add_step_analysis: "Add analysis step",
  add_step_filter: "Add filter step",
  add_step_report: "Add report step",
  update_combine_operator: "Change how steps combine",
  update_leaf_params: "Update parameters",
  update_step_metadata: "Rename step",
  replace_subtree: "Replace part of a strategy",
  get_estimated_size: "Count results",
  // Results and gene sets
  get_result_gene_lists: "Read gene list",
  get_sample_records: "Read sample records",
  get_download_url: "Prepare download",
  create_workbench_gene_set: "Save gene set",
  list_workbench_gene_sets: "List gene sets",
  export_gene_set: "Export gene set",
  lookup_gene_records: "Look up genes",
  resolve_gene_ids_to_records: "Resolve gene ids",
  // Verification and durable jobs
  run_control_tests_on_search: "Run control tests",
  check_study_step: "Check the study step",
  run_control_tests_on_step: "Run control tests",
  optimize_search_parameters: "Optimize parameters",
  run_gene_set_enrichment: "Gene-set enrichment",
  get_enrichment_results: "Read enrichment results",
  // The name the enrichment task itself puts on the wire.
  geneset_enrichment: "Gene set enrichment",
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
  // Research
  web_search: "Web search",
  literature_search: "Literature search",
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
    "Clear the strategy? This removes every step from this thread and from VEuPathDB.",
};

/** The approval question for one tool call, ready to render. */
export function approvalPromptFor(name: string): string {
  const bespoke = TOOL_APPROVAL_PROMPTS[name];
  if (bespoke !== undefined) return bespoke;
  return `${humanizeToolName(name)} needs your approval before it runs.`;
}
