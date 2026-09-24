AI Functions Reference
======================

Every function an agent can call, listed by the toolset that carries it. A
tool is a plain async function on a pydantic-ai ``FunctionToolset``; the
toolset an agent is built with decides what that agent is allowed to do. There
is no global tool registry: widening an agent means editing its toolset module.

:doc:`tools` documents the same functions from their source. This page is the
index by caller.

Lead
----

Built in :py:func:`pathfinder.ai.lead.lead_agent.build_lead_agent`. The Lead
runs the phases as tools and reads the ledger between calls. The building
tools stay hidden until ``classify_user_intent`` classifies the turn as one
that builds.

**Turn control**

- ``classify_user_intent`` -- Classify the turn. Called once, before any other
  sub-agent call.
- ``consult_user`` -- Ask the user a design question and block on the answer.
  Requires approval.
- ``read_ledger_section`` -- Full detail of one ledger section.
- ``get_live_strategy_state`` -- The strategy as it is now, bypassing the
  ledger's cache.
- ``remember`` -- Store an explicit memory for this user.

**Phase dispatch**

- ``frame_problem`` -- Run FRAME: operationalize the goal into a realizable
  ``OperationalSpec``.
- ``build_strategy`` -- Materialize the spec into a WDK strategy
  declaratively, with no LLM. Requires ``frame_problem`` first.
- ``edit_strategy`` -- Run BUILD against a strategy that already exists.
- ``recover_failed_steps`` -- Run the execution-recovery sub-agent on a failed
  build.
- ``verify_strategy`` -- Run VERIFY on the built strategy.
- ``clear_strategy`` -- Throw the strategy away. Requires approval.

**Comparison and control sets**

- ``compare_search_variants`` -- Run two or more search configs and compare
  their results.
- ``compare_variants_scored`` -- Run each variant as a scored experiment
  against a saved control set and rank them.
- ``build_control_set`` -- Validate gene IDs against WDK and save them as a
  reusable control set.
- ``list_control_sets`` -- The user's saved control sets for this site.
- ``read_gene_ids_from_gene_set`` / ``read_gene_ids_from_strategy``
  -- Read the gene IDs of a saved gene set or another conversation, to use
  as positive or negative controls. Neither saves a control set.

FRAME
-----

:py:func:`pathfinder.ai.tools.toolsets.frame.build_toolset`. FRAME proposes;
it never writes to WDK. ``set_criterion``, ``get_search_overview`` and
``get_parameter_options`` are enum-guarded to the searches actually discovered
this turn, so the model cannot invent a search name.

- ``get_record_types`` -- Record types for this site.
- ``search_for_searches`` -- Find WDK searches by description or keywords.
- ``browse_search_categories`` -- Categories and their example searches.
- ``list_searches`` -- Search names only.
- ``list_transforms`` -- Transform and combine operations.
- ``search_example_plans`` -- Public WDK strategies ranked by similarity.
- ``get_search_overview`` -- One search: description, parameters, dependencies.
- ``get_parameter_options`` -- One parameter: vocabulary and allowed values.
- ``lookup_phyletic_codes`` -- Species and clade codes for
  ``GenesByOrthologPattern``.
- ``list_saved_strategies`` -- Strategies the user saved on this site.
- ``set_criterion`` -- Bind a criterion to a search with resolved parameters.
- ``drop_criterion`` -- Remove a criterion from the spec.
- ``set_structure`` -- Fold the bound criteria into a tree.
- ``lookup_gene_records`` -- Gene records by name, symbol or description.
- ``get_strategy`` -- The current strategy graph.

BUILD
-----

:py:func:`pathfinder.ai.tools.toolsets.execution.build_toolset`. The only
toolset that mutates the strategy graph.

- ``build_strategy`` -- Materialize a complete strategy from one declarative
  tree.
- ``apply_operations`` -- Edit with a batch of operations instead of a whole
  new tree.
- ``update_leaf_params`` -- Partial patch of a leaf step's parameters.
- ``update_combine_operator`` -- Change a combine step's operator.
- ``update_step_metadata`` -- Rename a step. Local only.
- ``delete_step`` -- Delete a step and re-wire the tree. Requires approval.
- ``replace_subtree`` -- Replace the subtree rooted at a step.
- ``insert_saved_strategy`` -- Insert a saved WDK strategy as a combine input.
- ``add_step_filter`` / ``add_step_analysis`` / ``add_step_report`` -- Attach a
  WDK filter, analysis or report to a step.
- ``rename_strategy`` -- Rename the strategy.
- ``get_strategy`` -- The current strategy graph.
- ``request_search_inspection`` -- Inspect a search outside the commit set.

VERIFY
------

:py:func:`pathfinder.ai.tools.toolsets.verification.build_toolset`. Three of
these are durable: they defer to the worker and answer on a later turn.
``optimize_search_parameters`` also requires approval, because it launches a
sweep that runs for minutes.

**Results**

- ``get_estimated_size`` -- Result count for a built step.
- ``get_sample_records`` -- A sample of records from an executed step.
- ``get_download_url`` -- Download URL for step results.
- ``check_study_step`` -- Compare a study step's thresholds with what was
  asked.

**Controls and optimization**

- ``run_control_tests_on_step`` -- Control tests against a built step.
  Durable.
- ``run_control_tests_on_search`` -- Control tests against a standalone
  search.
- ``optimize_search_parameters`` -- Optimize parameters against control gene
  lists. Durable, requires approval.

**Gene sets and export**

- ``save_gene_set`` -- Save a gene set from a step or from a list of ids.
- ``list_gene_sets`` -- The gene sets the user saved on this site.
- ``export_gene_set`` -- Export a gene set as CSV or TXT.
- ``lookup_gene_records`` / ``resolve_gene_ids_to_records`` -- Genes by text,
  and known IDs to full records.

EDA
---

:py:func:`pathfinder.ai.tools.toolsets.eda.build_toolset`. The Lead carries
these directly; there is no EDA sub-agent.

- ``search_eda_studies`` -- Find a study by what it measures.
- ``describe_eda_study`` -- The study's entity tree and one entity's
  filterable variables.
- ``open_eda_analysis`` -- Open an analysis, so filters and computes have
  somewhere to live.
- ``set_eda_filters`` -- Set the whole subset of the open analysis.
- ``preview_eda_subset`` -- Count what the filters select on one entity.
- ``run_eda_compute`` -- Differential expression on the worker. Durable.
- ``create_eda_step`` -- Export the analysis into the strategy as a WDK step.

Shared
------

FRAME, BUILD and VERIFY all carry these.

- ``think`` -- An explicit reasoning scratchpad between tool calls.
- ``search_memory`` -- Search the user's cross-thread memory semantically.
- ``remember`` -- Store an explicit memory for this user.

Research (``web_search``, ``literature_search``) is on FRAME; VERIFY carries
``literature_search`` alone.

Deferred Tools and Approvals
----------------------------

Two mechanics change how a call ends.

- **Approval.** ``consult_user``, ``clear_strategy``, ``delete_step`` and
  ``optimize_search_parameters`` are declared ``requires_approval=True``. The
  SDK emits a ``tool-approval-request`` chunk and the turn waits for the
  user's answer.
- **Durable.** ``run_control_tests_on_step``, ``optimize_search_parameters``
  and ``run_eda_compute`` are wrapped with
  ``@durable_tool``. They defer to the worker and answer on a new turn.
  Each is registered ``sequential=True``: one parked call is checkpointed per
  turn, so a batch that fired two of them would leave the second unanswered.
