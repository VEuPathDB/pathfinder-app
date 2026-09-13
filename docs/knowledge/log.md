# Log

## 2026-09-13

* **One model judges every text this application did not write, and a judgement that
  does not happen has an answer of its own.**
  `assistant-core` 0.3.0a12 replaces the local injection classifier with
  `ModelInjectionJudge`, and `ai/capabilities/security.py` builds one judge for both
  trust boundaries: the scan the chat dispatcher runs on the researcher's message and
  the `screened_output` scan `ai/conversation/turn_runner.py` installs on every tool
  source. A judged injection in a message is 403 `FORBIDDEN`; a judgement that failed
  is 503 `SERVICE_UNAVAILABLE`, because an unscreened message reaches no agent. A
  judged tool result is replaced with the runtime's sentence, and one the judge could
  not read with this application's, so a provider blip loses one result and never the
  turn that ran the tool. Neither refusal names the judge, its confidence or the
  provider. `INPUT_SCREENING_ENABLED` gates both boundaries and
  `INPUT_SCREENING_MODEL` names the model; the api process screens the message and
  the worker screens the results, so both carry the pair. Both build the judge before
  they serve: the api warm-up reports `input_screening` in `ReadinessState`, failed
  with the provider's own message where the model cannot be resolved and absent where
  the deployment screens nothing, so a missing credential is a 503 at start and not a
  broken message; the worker, which serves no probe, raises `WorkerCannotScreenError`
  out of its entry point instead, because a worker that cannot screen would withhold
  every tool result of every turn. Under
  `PATHFINDER_CHAT_PROVIDER=mock` the judge runs on a scripted model that calls one
  marker string an injection, so the suite screens without reaching a provider.
  Nothing is downloaded or loaded any more: the image builds no model stage and
  `onnxruntime` is out of the lock. The approval-phrase test the runtime deleted with
  its classifier now lives beside its only reader, as
  `ai/graph/_lead_answers.py::is_pure_approval`.

* **The test tier and the chat debugger log the way a served process logs.**
  `tests/conftest.py::_configured_logging` calls `setup_logging` once per session and
  `devtools/chat.py::route_framework_logs_to_stderr` names the same processor chain, so
  `structlog.processors.format_exc_info` runs before the renderer on every surface. A
  logged exception is a string there, not a stack the console renderer expands with every
  local of the frame that raised it, and a record reaches stdlib logging, which is where
  a test reads one.

* **A turn the Lead classifies as off-topic reaches no tool, and has a budget of its own.**
  `ai/lead/intent_gate.py` offers such a turn nothing, `ai/lead/lead_pins.py` pins the
  two-sentence redirect after the turn briefing, `refuse_an_off_topic_essay` in
  `ai/lead/lead_agent.py` refuses a reply that carries a code fence or passes 400 characters,
  and `ai/lead/turn_budget.py::off_topic_budget_stop` ends the turn once such a run passes
  40000 tokens. The Lead's own run otherwise spends up to `Settings.lead_turn_token_limit`,
  600000 tokens, a sub-agent pass carrying a ceiling of its own. A run that reaches either
  ceiling ends with a sentence naming the budget instead of an error chunk, because the
  stream emitter re-raises the graph's control-flow signal and answers every other
  exception with an error chunk of its own.

* **A completion turn runs under the credential the durable call carried.**
  The runtime (`assistant-core` 0.3.0a10) opens the turn that answers a durable task inside
  the same carried job context as the task's body, so a WDK read or a second durable call
  made from that turn is authenticated as the researcher, on every path including the one
  that follows a failed body. Measured after the pin: an enrichment started by a completion
  turn reaches VEuPathDB and fails, if it fails, on its own arguments and not on a login.

* **The answers a consult carousel collected reach the turn that resumes it.**
  `state/useConsultAnswersStore.ts` holds them keyed by the approval they answer, and
  `features/conversation/rail/consultActions.ts::withConsultAnswers` puts each set on the
  request body as the `data-user-question-answers` part beside the consult call its own
  message answers, when `runtime/buildRequestBody.ts` builds the body. The send carries the
  answers whatever the message list holds, and an answered consult whose answers were never
  recorded throws instead of resuming the turn with none.

* **The revert dialog states the strategy rollback before the researcher confirms.**
  `features/conversation/content/BranchOrRevertDialog.tsx` says the strategy goes back to
  what it was at the reverted message and that a later version stays in the VEuPathDB
  account, which is what `services/conversations/revert.py::revert_conversation_to_message`
  does through `revision_ops.materialize_revision`. Workbench gene sets are what the revert
  keeps. The dialog's own vitest, `BranchOrRevertDialog.test.tsx`, asserts the sentence.

* **A saved gene set's WDK ids are read from the strategy, never typed.**
  `ai/tools/standalone/workbench.py::create_workbench_gene_set` takes the LOCAL step id
  of this conversation's graph, or none for the strategy's root, and reads the WDK
  strategy id, the WDK step id, the search name and the parameters off the last push
  (`services/strategies/sync_state.py`). A step the push does not name is refused with
  the steps it does hold, and a thread with no pushed strategy saves a pasted set whose
  message says enrichment has no background universe to recover.

* **A parked dispatch and the Lead's own durable calls are answered together.**
  `ai/graph/_lead_durable.py` builds one park carrying both groups and splits the
  workers' answers on the ids `parked.sub_agent.approvals` names: the sub-agent resumes
  with its half, the Lead with the rest beside the dispatch's delta, and a sub-agent
  that parks again carries the Lead's answered calls into the new park. Each call is
  answered once, so no job runs twice.

* **A tool that refuses every attempt stops the pass; it does not crash the turn.**
  `ai/lead/sub_agent_stream.py` records `PhaseStopReason.TOOL_RETRIES` with the tool's
  name and the words of its last refusal, and keeps the partial draft, so the Lead
  reports the refusal from the ledger the way it reports a budget stop. The library
  raises one exception class for many unrelated failures, so only the message that names
  the tool and the count it passed is absorbed; every other one still ends the run. The
  library's error text, its documentation URL and its validation dumps reach no thread.

* **A reply names the gene set an analysis actually ran on.**
  Each answered enrichment is recorded once, keyed by its task, against the user message
  the turn answers (`ai/graph/_lead_durable.py::enrichment_runs_answered`,
  `TurnMarkers.enrichment_runs`), so a later message is never judged by an earlier one's
  analyses. A reply is refused once per turn when an enrichment under that message
  failed on one set, a later one ran on another, and the reply names neither the
  analysed set nor its id. The Lead's instructions state that a task reporting
  `status: failed` is reported rather than routed around.

* **Only a filter and a seed are members of the combine a statement names.**
  `domain/strategy/combination_check.py::match_terms` reads a stated combination over the
  criteria a combine joins: a transform stands on the path to the root and an exclusion is
  subtracted from a branch, so neither is a member, and a statement left with fewer than two
  members gates no combine. `constraint_grounding` answers for the other two by their place in
  the tree: a transform grounds when it stands on the path from a named criterion to the root,
  an exclusion when it is subtracted from a branch that holds them, and the check abstains with
  its own note when either describes another tree than this one. So "A AND transform AND B" is
  honored by the tree it describes, "A AND B AND remove C" by `(A INTERSECT B) MINUS C`, and a
  tree that joins the named members at UNION is still refused.

* **A step's name never states a parameter value the step no longer holds.**
  `domain/strategy/step_naming.py::name_restating` restates, in one pass over the name the
  write found, every value the write moved, on the whole word and never inside one. A value
  the name carries twice, and one two parameters moved apart, identify no parameter and are
  left alone, because a stale name beats a fabricated one. `_apply_update_params` calls it, so
  every parameter write carries the matching name, and the push writes `custom_name` beside the
  search config when the plan says the name moved. The name a build writes is the criterion's
  text, which the model writes and no renderer can compose again, so the rewrite corrects only
  the words the write invalidated and needs no flag on the step.

* **One seam puts a write in the catalog's form before the guard reads it.**
  `services/strategies/stated_sides.py::canonical_batch` canonicalizes the values a batch
  writes and hands the stated-value guard both of its sides; `commit.py` calls it for every
  operation batch and `spec_build.py` for the tree a build writes, so `build_strategy`,
  `apply_operations`, the Lead's spec edits and `eda_step` are covered by construction. A value
  that departed from the spec before the turn began keeps its answer whichever wire form the
  write spells it in, and a genuine change of a stated value is refused on every path. The
  canonicalization writes a tree of its own, so a refused write leaves the caller's tree as the
  caller wrote it, and a value the catalog turns down is answered as a refusal by every caller
  rather than unwinding the turn. The tool layer states no sides of its own, and
  `StrategyMutationContext` carries no entry values.

* **One rule prunes the spec, wherever a step leaves the graph.**
  `domain/strategy/spec_reconciliation.py::spec_without_steps` is the invariant both
  entry points share: a combine left with one input is that input, a transform whose own
  criterion left is its input, and a criterion the pruned structure no longer names
  leaves the spec with it. `AgentToolState.drop_criteria_for_steps` calls it, so a
  transform whose step a delete removed collapses to its live input instead of taking
  the whole branch and the structure with it.

* **A gene set enriches the same way from either facade.**
  `services/gene_sets/enrichment.py::run_enrichment_batch` holds the whole addressing
  rule: a set with a step or a search reaches `EnrichmentService.run_batch` as it is, and
  a set of pasted ids reaches it as a temporary WDK dataset on the locus-tag search. The
  HTTP route's service method and the workbench facade the durable job calls both go
  through that one function, so neither repeats the rule and neither can lose it.

* **An EDA export follows the count of the subset it exports.**
  The preview is recorded on the thread's analysis (`conversation_analyses.subset_previewed`,
  revision `2026_09_13_0001`), and `ai/lead/pre_turn.py::attach_open_eda_analysis` reads the
  binding onto `StrategyDomainState.open_eda_analysis` at turn entry, so
  `ai/lead/intent_gate.py` offers `create_eda_step` for an analysis this thread counted on any
  message and withholds it where the thread holds no analysis or none was counted. A change of
  subset forgets the count in the same statement that counts the mutation
  (`services/eda/binding.py::apply_filters`), and binding another analysis restarts both, so the
  gate never opens for a number nobody took. Every writer of the subset states it the same way:
  the two filter surfaces through `apply_filters`, and a revert that puts another subset back
  through `services/eda/thread_surgery.py`, where a branch opens a document of its own and starts
  uncounted. The per-message `eda_previewed` marker is gone: no code read it after this rule, and
  a write-only marker states nothing.

* **A standing preference is one memory, however often it is stated.**
  `ai/tools/standalone/memory_tools.py::remember` writes a kind in `STANDING_MEMORY_KINDS`
  under `domain/memory.py::standing_memory_key`, a slug of the name the user gave it, so a
  second statement replaces the first and the retrieval carries no contradiction. The kinds
  that accumulate keep the minted key, and the reply says "Stored" or "Updated". The slug is
  cut to a length the store can index, and a name that carries no letter and no digit keys
  nothing: the tool asks the model for a name rather than writing every such preference into
  one bucket.

* **Site help names the organisms a site carries.**
  `assistants/site_help/agent.py::describe_site` reads the site's organism vocabulary through
  `veupathdb_mcp.gene_lookup.list_organisms` and groups it by the species each term names
  (`assistants/site_help/organisms.py`): the species with the most strains first, each with its
  strain count and up to three strain names, plus the totals. A term whose second word is an
  unknown epithet, or one that ends in `-like`, names an organism and not a species, so it stands
  alone with no strain line, and a term of two words is a species the site lists no strain for.
  One result carries the first `MAX_SPECIES` of them and says how many it left out; a genus
  argument answers with that genus alone, names the genus beside the counts it narrowed, and a
  genus the site does not carry comes back naming the genera it does, the way an unknown site id
  comes back naming the sites. The organism question is answered from the catalog rather than
  refused, and no answer reports a count of zero organisms for a site that has them.

* **A durable call in a process with no worker is answered in writing.**
  `platform/durable_worker.py::DurableCallsRefused` rides `agent_capabilities`, so inside
  `no_durable_worker()` a call to a deferring agent tool returns a refusal naming the tool
  instead of writing a task row and deferring a job nothing consumes. The name the model calls
  a tool by is not the name of the job it defers, so `durable_agent_tool` records the first
  where the two are bound and every durable tool of this application now defers through it.
  `devtools/chat.py` enters that block for an in-process run, so the turn finishes and its
  artifacts are written; a `--via-worker` run defers as before. The runtime half, a defer that
  raises leaving a task row behind, stays in the backlog.

* **A run's transcript names the calls the turn made itself.**
  `devtools/capture.py` reads `tool-input-available` and what settles it into the same row a
  sub-agent step writes, so `transcript.md`, `tools/` and the span tree carry an assistant's own
  tool calls under `lead` beside its dispatches. A turn that calls one tool and answers is no
  longer a transcript with nothing in it. The row settles the way a step settles: a failure
  decodes its errors and counts toward the loop the summary and the diagnosis both report, a
  success clears that count. A terminal call that answered draws no row, because the reply it
  carries is the transcript's own section; one that failed draws one everywhere, because a
  retried output is the loop a reader of these artifacts is looking for.

## 2026-09-12

* **A standing preference reaches every turn, whatever the request is about.**
  `ai/graph/_lead_turn.py::retrieve_memories` passes the runtime a `RetrievalScope`
  naming `STANDING_MEMORY_KINDS` (`domain/memory.py`): a kind listed there is read in
  full at turn entry and ranked ahead of the similarity search, so a default the
  researcher stated once is pinned on a request whose words do not resemble it. The
  similarity ranking keeps its own budget for the other kinds, and the answer holds at
  most the two added together. The runtime half is `assistant-core` 0.3.0a10.

* **A study search says how many studies it looked at.**
  `services/eda/catalog.py::search_studies` carries the catalog size and how the cards were
  ranked; `ai/tools/standalone/eda_catalog.py` summarises a semantic ranking as the K closest
  of M with the best match, and only a name match says "matched". Its guidance says a study
  named by author, title or accession that is not among the closest is not on this site, so
  the next step is to offer the closest or ask. With the run's call budget this replaces a
  reformulation loop that read one catalog thirty-seven times.

* **A discovery tool has a budget for one run.**
  `ai/agents/tool_vocabulary.py::DISCOVERY_CALL_CAPS` names the most calls one run may
  make to each tool that answers from a fixed catalog, whatever the arguments; the
  runtime's repetition guard refuses the call past the cap with a message that says to
  report what the tool returned, and ends the run on the next one. The two EDA catalog
  tools joined `READ_ONLY_TOOLS`, and the run diagnosis reads both refusal markers.

* **A cross-organism refusal names the remedy its own tree admits.**
  `domain/strategy/validate.py::cross_organism_refusal` reads the combine and the tree
  root: when a transform the combine sits UNDER maps its input into one of the two
  disjoint scopes, the refusal says to move that scope's criteria above that transform.
  A transform beside the combine holds none of its criteria, so only the path from the
  root down to the combine is searched, and the transforms on it are those whose output
  organisms differ from their primary input's. With no such transform the refusal names
  both scopes and asks for one, because widening a species to a genus leaves the two
  organism names as disjoint as before, and which scope sits in the secondary slot is a
  WDK wire detail. FRAME's structure guidance carries the same rule in one sentence.

* **A criterion takes only the role its search can play, and the tree says the same.**
  `set_criterion` reads `allowedPrimaryInputRecordClassNames` off the search definition it
  already fetches: a search that accepts no input step is refused the `transform` role, and
  a search that accepts one is refused every other role. A criterion that starts from a
  saved strategy is an input, so it is refused the `transform` role before the library is
  read. `set_structure` refuses a `transform` node whose criterion holds another role and a
  `leaf` node whose criterion holds `transform`, so the role decides the node kind that
  builds the step. Both gates sit in FRAME: the question needs catalog metadata, which the
  pure domain cannot read and the synchronous push validator has no site for. Every
  transform name the model is shown is recorded as seen, by `list_transforms` and by the
  refusal that offers the record type's transforms, so the name the refusal names passes
  the `search_name` guard on `get_search_overview`, `get_parameter_options` and
  `set_criterion` instead of being refused by it on the next call. Correcting the card:
  that guard's vocabulary is the names a listing recorded this turn, not the site's leaf
  searches, and `list_searches` already carries transform names into it; `list_transforms`
  was the one listing tool that showed a name it never recorded.

* **A turn starts from the strategy the graph holds.** A criterion that reached a step is
  addressed by that step's id, so `domain/strategy/spec_reconciliation.py` takes every
  criterion whose step the graph no longer holds out of the spec, collapses the combine
  left with one input and drops the structure left with none. A criterion reached a step
  when the last recorded build names it, which covers every id whatever minted it, or,
  for a spec whose criteria the record does not name, when its id carries the step
  minter's own shape; a criterion in neither set never had a step and stays, so an option
  criterion and an unbuilt one both keep their place. The build outcome is the authority
  here because the edit path writes its new step under the criterion id the model chose
  (`spec_to_operations::_node_for`), and only a full spec build renumbers criteria onto
  minted ids. The pre-turn applies the reconciliation before it hydrates and before it
  records `spec_before_turn`, so a spec it empties is re-derived from the live strategy
  and the spec an edit is diffed against states what the strategy states: a criterion
  re-bound over a step the editor deleted reads as `added` and not as `kept`. A turn that
  resumes a parked call keeps the spec that turn reached.

* **The stream writer takes the envelope and nothing else.** The turn runner keeps a
  payload only when it is the `{"chunk": {...}}` envelope `emit_chunk` writes, so the
  recalled-memories chunk goes through it and reaches the thread and the event log.
  `tests/unit/ai/graph/test_recalled_memories_reach_the_thread.py` parses every module
  under `ai/graph` and `ai/lead` and fails on a call of the writer of any other shape.

* **Enrichment and export of a saved gene set are calls the Lead makes itself.** The Lead
  carries `run_gene_set_enrichment` and `export_gene_set`, each on an id it can read from
  `list_workbench_gene_sets`, and the intent gate offers both before the turn is classified,
  beside the workbench save and listing: a request that names a set the workbench already
  holds asks for no strategy, so it waits on no build and no dispatch. VERIFY keeps its
  copies, enrichment still gated on a delta that earns it, for what a build just produced.
  The Lead carries neither `get_enrichment_results`, which reads an experiment's enrichment
  and not a gene set's, nor `get_download_url`, whose WDK step id the Lead has no way to
  read: a tool the Lead carries does what its docstring says, and the terms of a finished
  enrichment travel back on the completion call itself. The durable half is declared once and
  written twice, because the agent-side stub carries the deps of the agent that registers it
  and a test holds the two signatures identical: the Lead's own stub is what parks the turn,
  since a durable deferral is recorded on the deps of the run that made the call and
  `inner_context` hands a tool a fresh container the Lead's node never reads. A dispatch and
  a durable call of the Lead's own in one response are refused rather than parked, because
  the parked dispatch answers the sub-agent's calls only. The reversibility map is now the
  source of the durable line in the machine-guarantees pin, because a durable tool's declared
  job name and its agent-side name need not agree, and a test calls every tool the map marks
  durable to prove each one defers a declared job.

* **A study search answers as the ranking it is.** `search_eda_studies` reports a semantic
  top-k as "the K closest of M studies on this site (best match 0.72)" and says that a
  study named by author, title or accession that is not among them is not on this site,
  so the next move is to offer the closest or ask. Only a name match says "matched". M is
  the number of studies this account can see, counted where the ranking already walks the
  permission map and the listing, so the answer costs no second read. `StudySearch` carries
  the count and the ranking it used, and its guidance follows from the ranking rather than
  being passed beside it. `search_eda_studies` and `describe_eda_study` are in
  `READ_ONLY_TOOLS`, so the repetition guard watches them.

* **Every reader outside the tool package reads a declared name.** `_eda_stream_parts`,
  `_optimization_models` and `_export_models` are now `eda_stream_parts`,
  `optimization_models` and `export_models`, and
  `attach_export` and `parse_and_validate_inputs` lost their leading underscore, because a
  name a module outside the tool package reads cannot be private twice. The guard that held
  this for `ai/lead` and `ai/graph` now walks `pathfinder.jobs` too
  (`tests/unit/ai/test_the_tool_package_declares_the_names_others_read.py`), so a rename
  inside `ai/tools/standalone` fails a test rather than a durable job.

* **A saved conversation outlives the build that saved it.** The turn state drops a
  field the resuming build no longer declares and is rebuilt as this build's models
  at the turn's entry; a value the build cannot read ends the turn with one sentence
  the researcher can act on. Supersedes the strict-state decision: its refusal was
  swallowed by the checkpoint serializer and reached the researcher as an attribute
  error mid-turn.

* **The Lead reads only what the tool package declares.** A name of
  `ai/tools/standalone` that a module outside the package reads is now a name of a
  non-private module: `conversation_models`, `workbench_models`, `stream_parts`,
  `graph_helpers` and `strategy_refusals` lost their leading underscore, and
  `wdk_refused_the_edit` lost its own, because a name another package reads cannot be
  private twice. Nothing was re-exported and nothing moved between packages: each name
  stayed with the module that owns it, since every one of them is the tool package's own
  concept that the Lead also reads. What stays private is what only the tool package
  reads, at both levels - a module such as `_validation_helpers`, and a function such as
  `strategy_refusals._refused`, which its sibling tool modules call. The rule is held by
  construction: `tests/unit/ai/test_the_tool_package_declares_the_names_others_read.py`
  parses every module under `ai/lead` and `ai/graph` and fails on any import of a private
  module or a private name of that package, which covers the two modules the EDA sheet
  test pinned and the forty-three it did not.

* **A patched step and a written subtree state both sides of the stated-value guard in
  the catalog's own form.** The guard asks whether a batch introduced a departure from a
  value the spec states, so it compares what a step held with what the batch leaves
  behind. Those two were read in different forms: a push canonicalizes the graph in place
  (`services/strategies/step_wdk_push.py::_validate_plan_params`), while a patch and a
  written tree carry the model's form, so a vocabulary, tree or range parameter the
  catalog rewrites read as a departure the batch had not made.
  `ai/tools/standalone/_spec_edit_checks.py::canonical_sides` now answers both sides for
  the steps a write names: `update_leaf_params` hands it the step it patches and
  `replace_subtree` the stated leaves it writes, which it puts in the catalog's form
  first, and `StrategyMutationContext.entry_values` carries the entry side to
  `domain/strategy/spec_edit_guard.py::contradicted_values`, whose `held` argument is
  required so a new caller decides what it means. A value the batch leaves where it found
  it costs no catalog read, because both sides then carry one string; a value the batch
  writes over is read on the entry side too, which is what separates a rewritten wire form
  from a dependent vocabulary that moves a stated value: the first is applied, the second
  is refused. A parameter the write sends is answered for by the write. The other four
  paths into the guard (`build_strategy`, `apply_operations`, the Lead's spec edits and
  `eda_step`) still compare one form against the other, measured and carried as a backlog
  card.

* **A durable task whose worker was killed is settled by the sweep.** The runtime's
  stalled-job sweep closed the stream of a released `chat_turn:run` job and returned at
  once for every other job, so a killed `geneset_enrichment`, `run_eda_compute`,
  `run_control_tests_on_step` or `optimize_search_parameters` left its `background_tasks`
  row in an active status for good: the thread reported work in progress that nothing was
  doing, and the rail spun. The sweep now reports a released `durable:<tool>` job through
  the door the worker's own failure path uses, so the row leaves the active statuses, the
  thread reads the failure and the parked turn answers. A task that already recorded a
  result is delivered with it rather than failed, which also settles a worker killed inside
  the completion turn. The reason is worded for the work the job was doing, so a durable
  task reads "The worker running this task stopped". The change is the runtime's
  (`assistant-core` 0.3.0a9, `assistant_core/tasks/maintenance.py` and
  `assistant_core/tasks/runner.py`); this repository serves the row's failed state and its
  reason already, in `GET /api/v1/conversations/{id}/tasks`, the tasks rail and the trace's
  task row. The sweep settles work that no job lock protects, so the periodic job that runs
  it (`jobs/tasks.py::release_stalled_jobs_job`) carries
  `lock="maintenance:release-stalled-jobs"` and two runs of it never overlap.

* **A tail streams only while a live worker holds the thread.** The events route no
  longer reads "in flight" off the log's tip: `services/conversations/turn_liveness.py`
  answers it, and an open log counts as a running turn only when a procrastinate job locks
  that conversation and a worker is beating (`platform/health.py::worker_is_alive`, the
  heartbeat window procrastinate prunes its own workers by). The job alone does not say a
  turn runs: procrastinate releases nothing on its own, so a job outlives the worker that
  held it, and a queue no worker consumes keeps its rows for good. A chat turn and a durable
  call both take the thread id as their job lock, so the one read covers a queued turn, a
  running turn, a running durable call and the turn a finished durable task opens; the job
  table is read once per tail, by lock, through
  `persistence/repositories/thread_job.py`. A thread no live worker holds answers 204 and
  reopens as a static thread with its prompt, which PROTOCOL section 4 allows and the client
  falls back to the snapshot for. The tip is read before the job, which bounds a wrong 204 to
  the two statements a dispatch takes to log its prompt and to defer the job; a reconnect
  inside that window reads the snapshot and streams on its next reconnect. The card said the
  tip of such a thread is a prompt envelope; it is not. The dispatcher writes a
  `data-turn-status` chunk after the prompt, so the tip of a dead turn is that status or
  whatever chunk the worker wrote last, and the worker is what separates a dead turn from a
  live one.

* **An open EDA filter sheet is pinned until its subset is applied, and it is
  bounded.** The sheet carried every filterable variable of a study with its
  vocabulary, and the runtime's history elision took it: the three most recent
  tool returns stay whole and every older one is cut to its first 220
  characters, so a sheet the model copies from later was gone. Stripping the
  vocabulary from a second sheet for the same study assumed the first one was
  still readable, so the second sheet sent the values nowhere. The sheet is now
  one optional value on the thread's domain state, rendered in the Lead's
  instructions until the subset is applied or another study is opened; the Lead
  is the only agent that carries the EDA tools, so the pin is the Lead's, and
  the opening call answers with the pin's name alone, under the elision floor,
  so it is never cut. A pinned sheet is re-sent on every request, so both pins
  share one budget of 100,000 characters and one walk, and the two callers state
  different cut rules: FRAME never cuts its only sheet, because a search whose
  own sheet is over the budget has its vocabulary in no other place, while the
  EDA sheet is cut however few blocks there are, down to its variable names,
  types and examples, because `preview_eda_subset` reaches a variable's values
  one at a time.

* **A turn records every gene set it created, whichever agent created it, with
  what the researcher called it.** The created-set list had no production
  writer, so the `gene_set_note` auto-write never fired, and a note keyed by the
  set's id alone would embed nothing a researcher would ask for. The record is
  one list of `CreatedGeneSet` the turn owns: the Lead holds it, every
  `AgentDeps` the turn builds carries the same list, the tool body appends the
  id, the name and the size of the set it just saved, and the Lead's node folds
  it into the domain at turn end. Both registrations of
  `create_workbench_gene_set`, the Lead's and verification's, therefore leave the
  same record; the note is named and summarized from the set's own name and
  size; and the list is emptied once its notes reach the store, so the per-turn
  write does not grow with the thread.

* **A value the spec states is refused wherever the write carries it.** The
  stated values ride the mutation context, criterion by criterion, and they are
  measured on the entry graph and on the tree the write leaves behind, the way
  the joins already were. A parameter patch, a replaced subtree, a replaced
  strategy, an added leaf and a whole-tree build answer to the one guard, so a
  rewritten leaf that restates a user-stated gene id is refused with the value
  the criterion's words carry and the framing route (`set_criterion`). The
  build measures its tree before it replaces the graph, so a refusal costs
  nothing, and every seam that builds answers it: the build tool, the BUILD
  sub-agent and the saved-strategy insert each turn it into the retry the
  design promises, and the insert puts back the combine its splice had
  already wired. A value that already departed keeps its answer, except in the
  one shape the backlog carries, and a defaulted or FRAME-derived value stays
  editable. A patch reaches the graph canonicalized, so the stated value it is
  compared with passes through the same canonicalizer, and a catalog that
  rewrites a parameter the write never sent cannot read as a departure; that
  second look is asked for only when the patch names a stated value or the
  step does not already hold it, so a catalog that turns an untouched value
  down cannot turn a good patch into a parameter error. The per-operation
  check is gone: one guard, one place. A refused batch also restores every
  root, detached fragments included, so a rejected edit is a no-op on the
  whole graph and not only on the strategy's own tree.

* **A split graph reports one root's count, never a sum.** The graph snapshot,
  the strategy metadata, `get_strategy`, the Lead's live read and the build
  outcome all cite the same step: the single root when the graph has one, and
  otherwise the root the last push made the WDK strategy's root step. Root
  identity for the tree, the push and reachability stays with the structural
  root. The snapshot carries `detachedStepCount`, the steps the cited tree
  leaves out, which the thread draws as "N steps not in the strategy" instead
  of adding them in; a split graph names its fragments even when no root is
  citable. A root whose last push VEuPathDB refused reports no count, a split
  graph no push identifies reports none, and a graph with no steps reports
  none rather than a zero nothing measured. One sentence carries the count on
  every surface, so a build whose root has no number says "count not
  available" where it used to spend the missing count as a zero.

* **Every agent answers a refusal, and a defect ends the run wherever it
  happens.** One assembly attaches the refusal seam to each agent's capability
  list, and a test walks this application's packages for every `build_*_agent`
  it declares and holds the rule over each one that carries tools, so an agent
  added later is held by the same test rather than by a list someone remembered
  to extend. A correctable refusal then reaches the model as a retry naming the
  tool that lists the ids, on every assistant. The seam lives beside the errors
  it reads, which is the one layer the site-help pilot may reach: the pilot
  still imports nothing of the science. `ToolResilience` keeps the transient,
  WDK-refusal and permanently-unavailable branches and answers no other
  category: a refusal this application names belongs to the seam, and an error
  of no known category is a defect that propagates to the error path and the
  alert instead of becoming a tool result the model works around.

* **A question a sub-agent leaves open names the dimension it decides.**
  `FrameResult.open_questions` and `EditDelta.open_questions` carry typed
  `OpenQuestion` values, and a `FrameResult` that stops on the user is refused
  while any of its questions decides neither a dimension nor a recommended
  value, so the pass is asked again rather than recording a question the next
  turn can bind nothing to. `record_questions` stores what it is given rather
  than bare text at the default dimension. A message that abandons the request
  is then read as an abandonment: its requirements replace the thread's, the
  abandoned combination arms no structure gate, and only the organism the new
  goal states reaches FRAME.

* **A requirement is the user's word only where the user wrote it.**
  `UserIntent` carries no message text and `classify_user_intent` takes none:
  the tool records the prompt the turn was opened with, so a classification
  names the turn's own message. The requirements a classification states are
  attributed against that message: a value whose every word the message carries
  is the user's, and so is an organism the message names with the genus
  abbreviated, a combination whose terms the message carries, and a value the
  thread already holds from the user. Each of those is recorded
  `user_explicit`; every other value is recorded `assumed` and not hard, so it
  is surfaced in the ledger under its own heading and gates nothing. A turn
  whose build was never checked is offered `verify_strategy` and no other tool
  that writes once its first answer is refused, so the refusal has one way
  out.

* **A thread reopened while its turn runs follows that turn.** The snapshot
  says whether a turn is in flight: `AssistantClient.snapshot` answers
  `turnInFlight` when the last chunk it read is a prompt envelope, which is the
  shape a snapshot takes while a turn the host has not terminated is running.
  The thread view re-attaches on that fact as well as on a message a durable
  task left open, and tails from the snapshot's cursor, so a fresh tab draws the
  rows the turn has already logged and the ones that follow. A tail that answers
  204 leaves the snapshot standing, and a mount that found no running turn opens
  no tail, so a report of an idle thread cannot end a turn the user starts
  meanwhile. PROTOCOL 2.0.1 states the client rule.

* **A realized zero is a result, and a write may not restate the spec.** A build
  whose every step pushed and is valid needs no recovery, whatever count it
  reached: the build section derives `needs_recovery` and `recovery_kind` from
  the outcome's `fully_succeeded` alone, `empty_result_review` is gone, and
  `recover_failed_steps` leaves the Lead's tool list on a turn whose build did
  not fail, so a zero is reported and offered a change instead of dispatched.
  Independently, every write into the commit path is measured against the spec
  it realizes: a combine whose criteria the spec's structure joins at another
  operator is refused, whether the write is an operator change, a replaced
  subtree or a new combine. A combine that also brings a step no criterion
  states asks a question of its own and carries any operator, and only a
  contradiction the write introduces is refused, so a tree that already departed
  keeps its answer until something restates it. A parameter is user-stated when
  the criterion's own words carry its wire form or a requirement the user stated
  grounds onto that parameter, which is why a grounding now records the
  parameter it read and not only the value; every other value is FRAME's or the
  search's own and recovery may change it, which is what keeps `param_replan`
  alive. Both refusals name the framing route and tell the
  caller to stop and report. The card blamed a widened parameter on a
  user-stated value; the measured criterion states no size for it, so what
  answers that turn is the operator guard.

* **An open parameter sheet is pinned until its criterion is decided.** The
  sheet always carried every parameter's vocabulary; what lost it was the
  runtime's history elision, which keeps the three most recent tool returns
  whole and cuts every older one to its first 220 characters. A sheet is copied
  from many calls later, so it now lives in FRAME's state and is rendered in
  FRAME's instructions until the criterion binds or is dropped, and the
  sheet-opening call answers with the parameter template alone. A second sheet
  for the same criterion replaces the pin. A dependent vocabulary re-read under
  the bound parents replaces the entries it re-reads, and when the criterion
  never opened a sheet it is pinned as itself, under its own heading and with no
  template: a template built from a few dependents would omit the parameters
  nobody re-read. The pins are bounded at 100,000 characters; over that, the
  older sheets hold their parameter names and point at `get_parameter_options`,
  and the newest is never cut, because a search whose own sheet is over the
  budget has its vocabulary in no other place. The FRAME tool ceiling is
  unchanged: the per-parameter option reads the elision forced are what it was
  spent on.

* **A recreated step leaves the account with the strategy that dropped it.** The
  push carries out the WDK id every recreate replaces, and the commit deletes it
  in the same pass as the ids of dropped steps, after the step tree is put,
  because the put is what orphans them. A recreate whose push fails keeps the
  mapping it found, so the old id is neither deleted nor forgotten, and a put
  that does not land deletes nothing: WDK's tree still holds that step.

* **A refusal the model can correct reaches the model, not the user.** One
  capability on the Lead turns an `AppError` below 500 that is not an identity
  refusal into a `ModelRetry` carrying the code and the message, and a
  not-found also names the tool that lists the ids that exist, for the id the
  refusal itself names. An invariant failure, an outage, a sign-in and every
  non-`AppError` propagate, so what no other call can pass still ends the run.
  A lookup the seam can blame states the id it looked up in the refusal's
  detail, because a refusal that names no id names no listing tool either.
  The Lead was the only agent without such a seam: the three sub-agents already
  route a refusal through `ToolResilience`.

* **The memory kind that names a gene set says it is a note.** `gene_set_note`
  replaces `gene_set` across the vocabulary, the listing bucket, the wire and
  the settings labels, so `remember` can no longer be read as the save the
  researcher asked for. The save itself is `create_workbench_gene_set`, which
  the Lead can now call along with `list_workbench_gene_sets`; before this the
  Lead had neither, which is why a save reached the memory tool. Both join
  `remember` in the tools an unclassified turn is offered, so the first step of
  a save request shows every way to keep a set and not only the memory one.
  Nothing migrates a stored row: a memory of the old kind is simply not listed.

* **Only a message that abandons the request replaces what the thread
  states.** The requirements a thread has stated are cleared by a `new_strategy`
  message that answers none of the questions the thread asked and states a value
  of its own; every other message adds to them. A thread that recorded no
  question and ended waiting on the user keeps them whatever the message is
  classified as, because nothing there tells an answer from a restart. The card
  blamed the derivation for having nothing to merge with; the accumulator was
  already there, and the real cause was `record_intent` emptying it on any
  `new_strategy` message reaching a thread that had built nothing, which is
  every answer to a question asked before the frame closed.

* **A question the thread asks carries its recommended value in a typed
  record.** FRAME's own open questions and the Lead's `asked_questions` write
  the same record, and a reply that asks a question a framing turn recorded
  nowhere is refused. A recommendation no requirement replaces is accepted once
  and kept until a requirement on its dimension arrives, so it survives the next
  reply. It reaches the ledger and the sub-agents as a value the assistant
  offered, never as one the user stated: a combination only gates a tree when
  the user stated it. A requirement an earlier message stated says so in the
  pinned summary, and the FRAME work order names the request the answer belongs
  to, not the answer alone.

* **A draft thread reads nothing, and a turn in flight is not re-read.** The
  conversation is read only once it has a row: the caller opened on it, or an
  action in this tab created it. One pair of hooks in `state/` owns that
  question and every reader goes through them, and `beginConversation` is the
  one place that creates the row and records the id they wait for, so no read
  can race the create. The transcript is read only by a view that opened on a
  thread that already had one, because the snapshot of a turn in flight is cut
  at its prompt and reading it clears the record the transport replays that
  turn from. A revert opens the thread again, so the truncated transcript is
  read at the new mount.

* **A count nobody measured is sent as no count.** The graph snapshot and the
  strategy metadata carry `int | None` and read `citable_count`, so a step with
  a recorded push error or no measured size reports no number and the thread
  says the count is not available. A measured zero stays zero, which says the
  search matched nothing. The metadata read a `sync_state` attribute the graph
  never carries, so it reported 0 for every strategy; it now takes the session
  that holds it. The generated zod schema drops the lower bound when a field
  becomes a nullable union, so the Pydantic model is the only place that
  refuses a negative count.

* **A step runs the search it was created with.** A node whose search name
  changes is pushed to WDK as a new step and the tree is rewired to it, because
  the search-config endpoint validates the values against the step's own search
  and refuses a vocabulary from another one. The planner is the single place
  that decides this, so every combine above the replaced node is recreated with
  the new input id.

* **The strategy is re-rooted whenever the tree it maps to moves.** The commit
  puts the step tree to WDK when the WDK tree the graph maps to differs from the
  one the session recorded, not when the local shape changes, because a
  recreated step keeps its local id under a new WDK id. A step the strategy does
  not list after the put is a failed push, so an edit that leaves steps detached
  is reported instead of counted.

* **An edit WDK refused is the tool's answer.** A push failure inside the commit
  path is carried on the result as the answer WDK gave, with the status. A
  refusal of the values is a retry, because other values can pass; any other
  answer is the tool's own return. Every edit path answers this way: the step
  tools, `apply_operations`, the Lead's `edit_strategy` and the EDA export.
  `wdk_push_errors` stays what it is, the visible and resumable record of the
  last push of a step, and a push that lands clears it.

* **No count is reported for a step WDK refused.** The WDK step a refused push
  leaves behind still runs the previous search, so its size answers a question
  the strategy no longer asks. One rule decides it, `citable_count`, and every
  surface that renders or reasons about a count reads through it: the size tool,
  the step response, the per-node build result, the graph the agent reads, the
  live strategy read, the build outcome and the strategy summary. The commit
  marks the stored count unknown.

* **A criterion states only the parameters its sheet shows.** The spec derived
  from a live strategy reads the visible parameter names from the catalog, the
  same rule the parameter sheet applies, so a hidden or computed parameter the
  stored step carries is not offered back to a tool that refuses it.

* **The op takes the canonical values, not the envelope around them.** The
  in-place parameter edit builds its operation from the validated mapping the
  catalog answers with, so a parameter set holding a number is applied on the
  existing step instead of failing the operation's own validation.

## 2026-09-11

* **A tier preset names the roles of the assistant it belongs to.** A preset is
  a mapping from a role name to a model and an effort, and the registry is keyed
  by assistant first, so `site_help` has one role and PathFinder keeps four, and
  a new assistant adds a table rather than a field on a model every client must
  match. The tier registry is `pathfinder.platform.tiers`, because it serves
  every assistant and a one-agent assistant may not import PathFinder's agents.
  The site-help agent resolves its model the way the Lead does: the user's pick
  for that role, then the configured tier, then the model its own module names.
  The chat boundary refuses a role no installed assistant runs a model for,
  which is the same refusal a role outside the four used to get.

* **Both assistants are reachable from the product.** The conversations header
  names the assistants, the draft chat route carries the one the reader picked
  as `?assistant=`, and the message that creates the thread is the only one that
  names an assistant on the wire, because a thread keeps the assistant it was
  created with and another id on it is refused. A thread says which assistant
  answers it: the empty state before the first message, the sidebar row after
  it, and the model settings show the roles of the assistant in use.

* **Three library releases, taken together.** `veupathdb-py` is `v0.1.0a10`,
  `veupathdb-mcp` is `v0.2.0a7` and `assistant-core` and
  `veupathdb-mcp-conformance` are `v0.3.0a7`. The two Python pins move as one
  pair: a release of the tool server names the client release it was built
  against, so taking one tag while the other is behind fails the resolution on
  conflicting URLs rather than installing either.

* **Every client import names a published surface.** `veupathdb-py` declares
  sixteen surfaces and re-exports nothing from the module paths this backend
  used to read, so 1201 import statements now name a package or one of the
  eight published modules. Two test seams that reached a module for its globals
  reach a service of this application instead: the EDA doubles point
  `catalog`, `authoring`, `compute` and `binding` at one client, and the
  identity test records the site its own service names. The last private reach,
  the reset of the OAuth signing keys a test must not inherit, reads the name
  `veupathdb-py` publishes on `veupathdb.wdk` from `v0.1.0a10`.

* **The WDK to AST conversion belongs to the distribution that owns both
  shapes.** `build_snapshot_from_wdk` and `canonicalize_synced_parameters` are
  `veupathdb_mcp.wdk`, so a second consumer of a saved WDK strategy reads one
  conversion instead of copying 263 lines out of an application.

* **The record type a sample read asks for is this application's to name.** The
  tool server takes the record type a caller names and supplies no default, so
  the tool reads the type its own strategy session carries and falls back to
  `transcript` where the session has none.

* **A memory kind is a name the host declares.** The runtime holds a kind to a
  snake_case shape and nothing else, so the five kinds this product writes are
  one `Literal` in `pathfinder.domain.memory`, read by the routes, the tools and
  the spec. The wire keeps its enum: the memories routes publish this
  application's own value model, and a field the runtime adds to its own is
  published here or the release fails.

* **The turn driver names no product table.** An assistant declares a turn
  prologue that answers a token and a cancel hook that receives it, so a
  `site_help` turn makes no query against `strategy_revisions` and a stopped one
  restores nothing, while a PathFinder turn behaves as it did.

* **Three modules of mechanism left this repository.** The eleven turn and SSE
  instruments record from the runtime that observes each event, so the
  dashboards read `assistant.turn.*` and `assistant.sse.*` rather than nineteen
  empty `pathfinder.pipeline.*` and `pathfinder.sse.*` series; the write-through
  store and the task spawner are the runtime's, and the two stores subclass it.

* **Which assistant answers a turn is the runtime's rule.** This application
  keeps only how the refusal reads on the wire: an unserved id is 404
  `ASSISTANT_NOT_FOUND` and a request naming another assistant than its thread's
  is 409 `ASSISTANT_MISMATCH`, both rendered by a handler over the runtime's own
  exception.

* **The durable queue is a name this deployment declares.** `jobs/app.py` names
  `verification` and the worker subscribes to what `worker_queues()` lists, so
  the jobs stay on the queue they are already on and a worker written against
  the runtime's old constant fails at import rather than subscribing to a queue
  nothing defers onto. The three callers that defer a turn - the chat route, the
  debugger and the stalled-job fixture - call the runtime's own `defer_chat_turn`,
  which refuses a payload the stalled-job sweep could not read.

* **The prose the client bundle removed lives here.** The authority ranking, the
  two verification sites and the live enrichment test that is not evidence are
  `wdk/pathfinder/sources-and-authority.md`; the step-status derivation and the
  local-edit reading sit beside the divergences they explain; the procedure for
  listing every WDK call this backend makes is in `wdk/pathfinder/layer-ownership.md`.

* **A green unit run exits 0, because the suite loads no ONNX model.**
  `PIGUARD_ENABLED` is false among the root conftest's environment defaults and
  `warm_up_scanner` returns without building the session when it is false,
  which is the setting `scan_user_input` already read. The `onnxruntime` macOS wheel carries a
  telemetry client whose worker thread outlives interpreter finalization, and a
  reply that lands after the C++ static destructors ran locks a destroyed
  `recursive_mutex`, throws on a thread with no handler and aborts the process
  after the summary line, so a tier in which every test passed exited 134 and
  the gate ladder stopped there. A unit test that is about screening takes the
  `piguard_enabled` fixture, so the model still runs where the test is about the
  model, and the readiness probe reports a subsystem the deployment turned off
  as ready by policy rather than as loaded.

* **The tests tree is type-checked by the same two checkers, under the same
  rules, as the code it tests.** `[tool.mypy]` in `apps/api/pyproject.toml` and
  the repo-root `pyrightconfig.json` scoped both checkers to `src` minus
  `src/pathfinder/tests`, so a library release that widened a field type left
  every test comparing the old type silently wrong until a live run read a
  value the test never expected. Neither config excludes the tree now, so
  `uv run mypy src` and `uv run pyright src/pathfinder` are green only when the
  tests are green too. Reaching zero replaced the shapes that hid the error
  rather than the assertions: a tool return value is read through
  `tests/_support/tool_returns.py::returned` and its summary line through
  `summary_text`, which bind `ToolReturn.return_value` and `.content` to the
  shape the tool declares and raise an `AssertionError` naming what came back;
  a run context is the real `RunContext` the tool's signature states, built by
  the conftest factories, rather than a `MagicMock` behind a helper returning
  `Any`; an API route is the typed record `tests/_support/routes.py::ApiRoute`,
  whose `path`, `methods`, `dependant` and `body_model` are bound once instead
  of read off FastAPI's wide route context at every call site. Two wrong
  product annotations surfaced and were corrected, and one integration test was
  found seeding a column on the wrong model, so the condition it names was
  never created. Both baselines hold only what is still true: an entry leaves
  either file when the offender goes, and no entry was added.

* **The active conversation row's meta line is full foreground, and a `motion`
  entrance paints settled under reduced motion.** The row is tinted with the
  site's primary, so the timestamp is a foreground tone read against that tint
  and axe holds it to 4.5:1. An alpha on that tone leaves the ratio near the
  gate on every palette, close enough that a later change to the tint walks it
  under; full foreground clears the gate by more than a factor of two, so the
  row survives a palette that moves. A `motion` entrance is JavaScript, so the
  CSS rules that zero transitions and animations under
  `prefers-reduced-motion: reduce` do not
  reach it, and a row caught mid-entrance reads at a fraction of its opacity,
  below the ratio, for an audit and for the viewer. `lib/motion.ts` owns the
  rule: `usePrefersReducedMotion` reads the preference, and `useEntrance`
  returns the entrance untouched or, under the preference, `initial: false`
  with a zero-duration transition, so the element paints at its `animate`
  values from the first frame. Every `motion` entrance in the app reads its
  `initial`, `exit` and `transition` through that hook; an element that keeps
  its own reduced-motion branch states the rule a second time and will drift
  from it.

* **The option a criterion states rides the step that runs its search.** A
  framed spec stated `gametocyte_expression` and `gametocyte_timecourse_option`,
  both on `GenesByRNASeqEvidence`, with a structure over the first alone; the
  build minted one step and pushed `dataset=all_rnaseq`, the search default,
  where the request asked for `pfal3D7_Gametocyte_Timecourse_rnaSeq`, so the
  count answered a broader question than the one asked.
  `operational_spec.py::fold_option_criteria` now moves the values a criterion
  with no step states onto the criterion that names the same search and drops
  those names from its defaulted list. A value the carrier's own text states
  holds; a value it defaulted or FRAME assumed is overridden, because an
  assumption is the value the model chose and the option is the one the user
  states. The carrier keeps the text that names its step, and each moved value
  rides as an `AssumedValue` whose reason is the option's text and whose
  `carried_from` names the option, replacing any assumption the carrier held for
  that name, so the constraints show the user's choice and not the model's
  guess. An option no single criterion in the structure carries is reported
  unplaced, and so is one that restates a parameter an earlier fold already
  carried with a different value; a second option that states the same value
  carries nothing more. The two seams that
  take a spec the model just wrote refuse an unplaced option:
  `build_strategy` and the new side of `run_edit` raise
  `dispatch_messages.py::option_binds_no_step_message`, which names the option
  and the criteria that run its search, or the parameter and both values when
  one criterion runs it. The stored side of `run_edit`
  folds leniently, because a spec an earlier turn left is not this turn's
  statement, and the edit stores the folded spec beside its commit so a build
  and an edit leave the thread the same spec. FRAME's instructions now say that
  a choice inside one search is a value in that criterion's `params` and that
  the tree names every criterion that stands for a search of its own.
  `structure_criteria` moves to `operational_spec`, where the structure lives.

* **A stated combination of three or more terms is checked at every combine it
  names, not only where the terms meet.** "kinases OR mass spectrometry
  evidence OR DeRisi expression" against `UNION(kinase, INTERSECT(mass spec,
  DeRisi))` returned no violation: the three criteria meet at the root UNION,
  which carried the required operator, so a tree that answers "kinases OR (mass
  spec AND DeRisi)" passed the check and reached the user as the strategy they
  asked for. `combination_check.py::combination_violation` now reads the
  meeting node and every combine under it whose criteria are two or more of the
  named ones and nothing else, so the same tree is refused and
  `UNION(kinase, UNION(mass spec, DeRisi))` is accepted at any depth. A combine
  that also holds a criterion the statement does not name answers a question of
  its own and stays unconstrained, so the check never refuses a tree for
  evidence the user did not talk about. Two-term statements read exactly as
  before: no combine below their meeting node holds two of the two. The
  intent-gate docstring on `classify_user_intent` states that the terms of one
  constraint are one flat group, so a nested shape is stated as one constraint
  per group. One rule, `combination_check.py::_brought`, says what a branch
  brings to a combine, and both the meeting node and every combine under it
  read it: a transform the statement names stands for its whole input, and any
  other transform brings what its input brings. So
  `UNION(kinase, INTERSECT(orthologs of mass spec, DeRisi))` is refused under
  "kinases OR mass spectrometry evidence OR DeRisi expression", which names the
  mass spec, and refused under "protein kinases OR vivax orthologs OR DeRisi
  expression", which names the orthologs; the second returned no violation
  while the branch reported the unnamed mass spec and took the exemption.
  `operational_spec.py::criteria_under` keeps its one reading, the criteria a
  subtree states a step for, which `stated_shape.py::structure_criteria` reads.

* **The thread title is written at one defined point of a turn, so the SSE
  golden pins an order the runner guarantees.** `run_turn` used to carry the
  title opportunistically: `_handle_custom` checked `title_task.done()` on every
  chunk the graph streamed and wrote `data-conversation-title` on the first one
  that arrived afterwards, so the position followed the scheduler. The same
  prompt on the same build, with only the cost of the title task changed, put
  the chunk at index 4 when the title was ready immediately and at index 7 when
  it took 0.4 s, in a turn of 24 chunks that was otherwise identical, and
  `chat_sse_golden_simple_turn.json` recorded whichever one the recording
  machine produced. The runner now writes the title after the epilogue and
  immediately before `finish`, awaiting the task there under
  `_TITLE_WAIT_SECONDS` (15) so a slow title model cannot hold the turn open;
  a title past the wait is dropped with a warning and the next turn names the
  thread. `PROTOCOL.md` states no position for the part and states "before
  `finish`" for its two conversation-level neighbours, and the web client reads
  it by kind, so the rule follows the protocol without changing it. Recorded as
  `decisions/the-thread-title-is-the-last-chunk-before-finish.md`. Proven by
  `tests/integration/chat/test_conversation_title_position.py` (a title ready at
  0.0 s and one ready at 0.4 s both land at `len - 3`, and a title past the wait
  is cancelled at the ceiling and leaves a turn that still finishes with
  `stop`), and the golden was re-recorded
  once through `PATHFINDER_RECORD_GOLDEN=1` and now asserts the last three chunk
  types by name. Four hand-rolled turn drivers in `tests/integration/chat`
  became one `_helpers.py::run_one_chat_turn` for the two that drove a plain
  turn; the two files that post their own body (a named assistant, a shared
  client) keep their own shapes.

* **The search listing carries names only, and the scripted FRAME survives a
  compaction of its own history.** On veupathdb.org `list_searches` returned
  2769 `{name, displayName}` rows, 574624 characters and about 143656 estimated
  tokens against a `COMPACT_AT_ESTIMATED_TOKENS` of 100000, so the FRAME
  history was rewritten on every model step. One build of a single criterion on
  the portal made 82 tool calls, 36 of them `set_criterion`, compacted 76 times
  and hit the 40-request ceiling twice; the edit turn that followed replied
  "Substituted the organism" while the AST leaf still read
  `Plasmodium falciparum 3D7`. The tool now returns the names and nothing else,
  50248 estimated tokens, pinned by
  `tests/unit/ai/tools/test_catalog_listing_size.py`, which asserts that a FRAME
  history carrying a portal-sized listing is left uncompacted and that the same
  history with the display names is not. Recorded as
  `decisions/the-search-listing-carries-names-only.md`. The mock is fixed on its
  own side: `ai/models/mock/history.py` reads the work order from the head
  request's first user prompt and counts the calls a digest records as calls
  already made, so a compaction no longer restarts the build arc. The same two
  turns now make 6 and 5 tool calls, compact nothing, log no usage ceiling, and
  the AST leaf reads `Plasmodium vivax P01`.

## 2026-09-10

* **A criterion that binds an option on another criterion's search has no step,
  and no refusal may ask it for one.** A framed spec stated three criteria and
  a structure over two of them; the build minted two leaf steps, and the third
  criterion, which names a parameter option on one of those searches, kept its
  framing id. `edit_strategy` then refused three times with "criterion
  'gametocyte_timecourse_option' names no step in the strategy" and the turn
  ended as `UnexpectedModelBehavior`, because the edit path and the leaf-set
  invariant both measured the graph against every criterion. The refusal
  predates the shared invariant: the code at `95503633` refuses the same shape
  with the same words. `stated_shape.py::criteria_with_steps` now states which
  criteria answer to a step, and the edit path plans no change and no delete
  for a criterion that has none. The same rule re-arms the subtree guard, which
  one such criterion used to disarm for the rest of the thread. The two write
  paths read the rule against the step ids the graph holds once the batch
  applies, so an edit that adds a filter and changes an existing step is no
  longer refused for adding a step the spec was about to state.

* **A tool past its retry ceiling is answered, not removed, and the tool server publishes the search-details resolver.** `ToolResilience` used to drop a tool's `ToolDefinition` once its retry count reached the threshold, so the call the model had already chosen resolved against the filtered list, raised `Unknown tool name` at the retry maximum, and ended the turn as `UnexpectedModelBehavior`; a 14.5 minute DNS failure inside the compose network ended two turns that way, one after 240.322 s of work. The filter is gone and `on_tool_execute_error` returns `_outage_directive` on the call at the ceiling, naming the search when the call carries one and the tool when it does not, so the model reads a sentence and picks another search. Recorded as `decisions/a-tool-past-its-retry-ceiling-is-answered-not-removed.md`. Separately, `veupathdb-mcp` moves to v0.2.0a4, which publishes `resolve_search_details` on `veupathdb_mcp.catalog`: the four test seams that patched the private name now go through one helper, `tests/_support/catalog_builders.py::serve_search_details`, and the sixth layering contract holds 20 ignored imports instead of 22.

* **Every subtree write holds the leaf-set invariant, not just the edit path.**
  `replace_subtree` applied whatever tree the model sent once the step id
  existed, so a recovery pass replaced a seven-step kinase branch with four
  steps named `__input_step__` and the four kinase criteria left the strategy
  while the spec still stated them. The invariant the edit path already held is
  now one implementation, `domain/strategy/stated_shape.py::stated_shape`, with
  two call sites: `spec_to_operations.py::_refuse_a_shape_the_edit_did_not_state`
  and the subtree write, which measures the shape on a copy and raises a
  `ModelRetry` naming the criteria that would be lost instead of committing. A
  placeholder name is refused a step earlier: the tool arguments are typed
  `StepTreePayload`, so a tree carrying a `__name__` sentinel other than the
  combine one never validates.

* **The invariant now sits where no caller can go around it, and stops
  refusing writes that keep every criterion.** `apply_operations_and_commit` is
  the one place a batch reaches the working graph, so any batch that replaces a
  subtree is measured there against `StrategyMutationContext.stated_criteria`
  and restored on a violation; `apply_operations` turns that into a
  `ModelRetry`, and its `operations` payload is held to the same placeholder
  rule as a step tree. Two false refusals are gone with it: a criterion that
  references a saved strategy is measured as the one criterion it is rather
  than as the leaves the expansion brought, and a criterion whose step an
  approved `delete_step` removed leaves the spec with it, so the criteria and
  the live steps stay in one address space and the guard stays armed for the
  rest of the thread. The placeholder rule reads the search name only, because
  a criterion's own text becomes the display name.

* **A saved strategy and an exported analysis are each one criterion.** The
  measurement read the combine marker WDK puts on a collapsed reference, which
  a spec whose only criterion is a saved strategy never produces, so its build
  was refused for the leaves the expansion brought. It now reads the criteria:
  a stated step holding no other stated step addresses its whole subtree.
  `create_eda_step` states the leaf it wires into the main tree as a criterion
  of its own, so the export no longer leaves the spec and the graph in two
  address spaces, where every later `replace_subtree` on the thread was refused
  for a step no criterion stated while a subtree that dropped the exported step
  was applied.

* **A write into an input slot never evicts the step that slot holds.** An
  export into an occupied slot filled it anyway: the add sets the slot whether
  or not it is free and reports no dropped step, so a stated step left the tree
  undeleted, with no record of the loss, and every later write on the thread was
  refused for the criterion it answered. `create_eda_step` now refuses an
  occupied slot with a `ModelRetry` naming the slot, the step that holds it and
  the criterion it answers, and the choke point holds every other producer to
  the same rule: `apply_operations_and_commit` records the occupant of each slot
  an operation overwrites and restores the graph when one of them ends the batch
  off the tree and undeleted. A rewire that puts the occupant under the step
  that replaces it is untouched, which is the shape `spec_to_operations` emits
  when a new criterion joins a branch that already exists.

* **The placement sweep's card left the backlog.** Every module the sweep
  ranked had already moved, and the three lines it still carried are now each
  somewhere that can be acted on. The two duplications are decided rather than
  removed: `CamelModel` stays written in `assistant_core.platform.pydantic_base`
  and in `veupathdb.model`, and the testcontainers bootstrap stays written in
  each repository's own conftest, because the two distributions may not depend
  on each other and a third distribution for a twenty-line base class and a test
  fixture is a pin every consumer pays for one class
  (`assistant-platform: docs/knowledge/decisions/the-model-base-and-the-test-database-are-written-per-distribution.md`,
  which also names the embedder drift gate as the shape to copy if the two
  `CamelModel`s ever separate). The library that still names PathFinder was
  already the ranked card `re-cut-the-authoring-model-out-of-veupathdb-py.md`.
  What the sweep's enforcement paragraph carried is now its own card: the tool
  server declares almost no public surface, and this application imports 66
  names out of `veupathdb_mcp`, 52 of them submodules no package publishes.

* **The conformance account hook opens its own WDK client.** The nested
  conformance session runs in a worker thread under its own `asyncio.run`, and
  the per-site `VEuPathDBClient` this process caches keeps a live connection
  bound to the loop that created the run's step. Listing the account's
  strategies through that cached client raised `RuntimeError: ... is bound to a
  different event loop`, which errored the three family 3 checks that read the
  account and made the admission record read `fail`. The hook now builds a
  client for the snapshot and closes it, so nothing crosses a loop; the record
  reads `incomplete` again with the three named gaps.

* **The runtime owns six more tables, and this application deletes its copies of
  them.** `assistant-core` and `veupathdb-mcp-conformance` move to `v0.3.0a4`
  and `@veupathdb/assistant-client` follows the same tag. `monthly_usage`,
  `chat_turn_cancellations`, `scratchpad_notes`, `scratchpad_compactions`,
  `background_tasks` and `task_progress` are declared by
  `assistant_core.persistence.models` on the `Base` this application already
  maps on, so its own declarations, their repositories and their tests left in
  the same change as the pin: two models on one `MetaData` is an import error,
  not a warning. The tables stay in the database and the runtime's revision
  `2026_09_09_0004` adopts them, so no new revision was written here and the
  historical ones stay as that database's history. `OWNED_TABLES` is ten names,
  which the autogenerate filter already read, so `CARRIED_DRIFT` and its
  parametrized test are deleted: a revision generated against a database this
  entry point built now carries no operation with no exemption at all. An
  adopted table keeps the DDL this chain gave it, so the runtime's own view of
  those tables reports column types and index names that differ from its models.

* **Quota, pricing, thread ownership and turn cancellation are the runtime's.**
  `services/quota.py`, `ai/pricing.py`, `services/conversations/authz.py`'s
  general half, `services/conversations/cancellation.py` and the stop
  repository are deleted for `assistant_core.quota`, `assistant_core.pricing`,
  `assistant_core.conversation.authz` and `.cancellation`. The budget is an
  argument: `services/users.py::effective_monthly_limit_usd` reads the account
  override or the configured default and the two callers pass it, so the 429
  stays where it was. The runtime raises without a status, so
  `platform/error_handlers.py` maps `ConversationNotFoundError` to 404
  `STRATEGY_NOT_FOUND`, `ConversationForbiddenError` to 403 and
  `TurnStillRunningError` to 409 `SESSION_CONFLICT`, and the `AppError`
  subclass is gone. `pathfinder.persistence.repositories.conversation` now
  holds the runtime's thread store and reads the strategy projection beside it
  in a second query, so this repository writes no `select(Conversation)` at
  all and re-implements no ownership predicate: the strategy write asks the
  runtime's `get_by_id` whether the thread still stands. The lookup that also
  reads the strategy stays here, because the projection is this product's
  table.

* **The scratchpad is the runtime's and the coaching is this product's.**
  `ai/scratchpad/`, `domain/scratchpad/`, the notebook and the note repository
  are deleted. The three sub-agents call
  `build_scratchpad_toolset(guidance=PATHFINDER_SCRATCHPAD_GUIDANCE)` and the
  index renders under the same guidance, whose third string is the sentence
  `promote_to_memory` used to carry in its docstring; an empty one would leave
  the runtime's generic description, so a test pins the sentence on the tool
  definition. `ai/graph/nodes.py` hands `compact_scratchpad` the compactor
  factory rather than a built agent, so the model is built only on a turn that
  compacts, and revert and fork call `delete_notes_from` and
  `copy_notes_for_fork` instead of writing statements against the runtime's
  tables. Two differences to expect: `delete_note` and `promote_to_memory`
  refuse a no-thread turn with a payload where they returned a sentence, and
  the empty index puts the host's guidance after a blank line.

* **A durable tool is declared once, and the worker installs the seams.** The
  decorator, the runner, the progress emitter, the completion turn, the
  maintenance sweep, the heartbeat thread and both task tables are the
  runtime's. Each of the four tools is one `declare_durable_tool` beside its
  agent-side definition, so the decorator, the procrastinate job and the
  worker-side body cannot drift apart; a registration naming a tool nothing
  declared is refused at import. `jobs/worker.py` installs the procrastinate
  application, the assistant registry, the completion turn, the worker context
  and the carried WDK token, then starts the runtime's `HeartbeatThread`.
  `Settings` drops `worker_heartbeat_interval_seconds`,
  `worker_dead_heartbeat_seconds` and `worker_stalled_job_timeout_seconds`,
  which are `RuntimeSettings` fields validated against each other; the
  environment variable names do not change. The WDK token rides the job as a
  `CarriedSecret` on a `DurableJobState` subclass rather than a named field, so
  the durable job's kwargs changed shape while its name did not:
  **drain the `verification` queue before the deploy that takes this release.**
  `jobs/logging_filters.py` keeps its one key, for `chat_turn:run` only.

* **The runtime brings its own migration chain, and this chain stops proposing
  its tables.** `assistant-core` and `veupathdb-mcp-conformance` move to
  `v0.3.0a1`. `pathfinder.platform.migrations.upgrade_all` runs
  `assistant_core.migrate.upgrade_head` after this application's chain and the
  tool server's, on the same connection, because `conversations.user_id`,
  `memory_tombstones.user_id` and `conversation_events.task_id` name tables
  this chain builds; the runtime's baseline no-ops on a database that already
  holds all four of its tables and stamps `alembic_version_assistant_core`. The
  shared declarative `Base` puts those four in this chain's `target_metadata`,
  so `alembic/env.py` now passes an `include_object` that drops them and the
  runtime's version table, reading `assistant_core.migrate.OWNED_TABLES` rather
  than a second copy of the names. The filter also refuses the tool server's two
  index tables and its version table, procrastinate's queue tables and
  LangGraph's eight checkpointer and store tables, so a revision generated
  against a database this entry point built carries no operation outside the
  four tables that leave with the next runtime release;
  `conversation_strategies.strategy_ast` maps the `JSONB` the chain built rather
  than `JSON`, which was the last column this application's models and its chain
  disagreed on outside the tables that leave with the next runtime release. On a
  fresh database the two chains agree on every column of the four tables and
  differ only in six operations over six index names, which this application's
  chain wrote first. The one process that installs both
  embedder copies now gates their drift: three module pairs compared with the
  distribution names normalized, the two constants, the four settings defaults,
  and the `1024` both alembic chains build the vector column at.

* **The TypeScript client is published under the organisation's scope, and four
  readers moved into it.** `@pathfinder/assistant-client` becomes
  `@veupathdb/assistant-client` 0.3.0-alpha.1; the dependency key, the
  `workspace=` name and the tag move together, and every import, the boundary
  allow-list and the transpile list follow. `thread/traceParts.ts`,
  `sessionUsage.ts` and `thread/runningPhase.ts` are deleted for the package's
  `toTraceParts`, `threadUsage` / `turnUsage` and `runningPhase`;
  `DataBackgroundTaskStarted.tsx` keeps its `laneOf` and hands it to
  `taskLifecycle`; `TraceAnchor.tsx` reads a call through `isToolPart` and
  `taskExhibit.ts` reads a step through `readSubAgentStep`. The composer's
  fields are now `total.tokens` and `total.costUsd`. Two rules change with the
  move: the package reads the wire's declared types, so a count sent as a
  string totals as nothing, and a dispatch payload that names no phase still
  counts toward its turn. An assistant-ui part names its kind beside its type,
  which the protocol does not, so `features/conversation/parts.ts` maps one to
  the other before the package's readers see it.

* **A mount no longer tails a thread that has nothing to tail.** Every
  conversation named in the URL re-attached on mount, so an idle thread held an
  open `GET /events` while the user typed. `ai` 7 answers that tail's 204 by
  setting the chat-wide status to `ready`, which `ai` 6 did not, so a turn sent
  inside that window lost its `submitted` status: the composer showed Send
  instead of Stop for the turn's whole length, the thread drew no running turn,
  and `expectIdle` in the e2e harness passed 75 ms after the click. The reattach
  query in `useChatRuntime` is now enabled only when the snapshot read left an
  open message in the shared cursor store, so an idle thread opens no tail and
  a suspended turn still resumes. The guard is in the hook that owns the query,
  not at its call site, so no caller can ask for an unconditional tail.

* **A dispatch that runs more than one pass reports the sum of them.** The
  Lead's per-call accounting kept the last pass alone, so a FRAME pass that
  continued after a budget stop replaced the earlier pass's tokens on its
  `data-sub-agent-call` card. The thread's turn chip sums those cards, so it
  read less than the turn's own `data-turn-usage` and the persisted message
  metadata. `absorb_sub_agent_usage` now adds each pass into the dispatch's
  `SubAgentCallUsage`, and a pass that continues one reads that total as its
  baseline, so the running card never drops either.

* **The authoring model came home.** `veupathdb-py` v0.1.0a7 keeps seven WDK
  shapes in `veupathdb.domain.strategy` and nothing else. The strategy session,
  the fifteen edit operations, the spec, the constraints, the spec diff, the
  combination check, the build outcome, the sync-state protocol and the step
  lifecycle now live in `pathfinder/domain/strategy/`, with their 117 tests
  beside the eight modules already there; the stored container
  `PersistedStrategyGraph` sits in `pathfinder/persistence/models.py`, which is
  where the row it parses is read. `OpenSlot` split: WDK states a parameter
  with no bound value, so `veupathdb.domain.parameters.unbound.UnboundParameter`
  carries the name, the question and the options, and the criterion that holds
  it stays here as a subclass. `docs/knowledge/decisions/the-client-library-is-a-distribution.md`
  states the outcome in place of the accepted risk, and `step-status-is-derived.md`
  names the module the derivation now lives in.

* **The tool server publishes what a host reads, so this application stopped
  naming its files.** `veupathdb-mcp` v0.2.0a3 declares thirteen surfaces over
  268 names, and every import here reads a name from the package that publishes
  it. `run_step_control_tests` returns a `ControlTestResult`, so the worker
  reads the two control sets by name and validates a `ControlOutcome` out of it
  for the export; `summarize_intersection` replaced a private helper a service
  had been reading; `intersection_ids` is None when a control set is over the
  answer-page limit, which is a state, not an empty list, so the four gene
  lists read it as one; the autogenerate filter reads `OWNED_TABLES` and
  `VERSION_TABLE` from `veupathdb_mcp.migrate` instead of a retyped literal and
  a metadata spread. The sixth import-linter contract now names every deep
  module of the tool server, so a file-path import fails `lint-imports` rather
  than a release.

* **A cross-repository citation resolves or fails.** `scripts/check-knowledge.mjs`
  is the shared copy that reads a `repository: path` citation against the
  sibling checkout: present and resolving is silent, present and missing is a
  failure, absent is unverified and never a failure, so CI still passes with no
  siblings. Three citations here were prose, not paths: a deleted acceptance
  tree, a test that moved into this repository with the spec it covers, and the
  citation form quoted as an example.

## 2026-09-09

* **A blank entry in `config.toml` is no entry.** `TomlConfigSettingsSource`
  passed a blank string through, so a placeholder line in the file overrode the
  default the field declares. The source now skips a blank value, which is what
  `env_ignore_empty` already does for the environment and dotenv sources, and it
  takes the file it reads as an argument so a test can hand it one.

* **Literature and web search are served over MCP, and the two research
  directories left this tree.** `services/research/` (1935 lines),
  `domain/research/` (485), `ai/tools/standalone/research.py`,
  `_research_models.py` and `assistants/_stub_services.py` are gone; the same
  clients are served by `veupathdb-research-mcp`, the second entry point of the
  `veupathdb-mcp` distribution, on port 8110. `platform/tool_sources.py` admits
  it beside the WDK server, `pathfinder_spec.py` declares it as the `research`
  source, and the runtime's prefix makes the model call
  `research_web_search` and `research_literature_search`. The declaration is not
  required, so a deployment that configures no endpoint or credential runs the
  turn without those two tools; that is what mock mode is. Both shipped
  assistants now declare a source, so `turn_runner` no longer guards on
  `spec.tool_sources` and every turn enters the resolver, which opens nothing
  for a spec that declares none. The citations that
  rode `source-url` chunks are now the `data-research.sources` part, drawn by
  `content/parts/DataResearchSources.tsx`. The shape and the two rejected
  alternatives are in
  [the research tools are served by a second server](decisions/two-servers-from-one-distribution.md).

* **Plan counting, the frozen gene-set step and the WDK step-tree fold are the
  library's, and this deployment names the strategies they write.**
  `services/strategies/wdk_counts.py` keeps only its plan hash and its LRU and
  calls `veupathdb_mcp.wdk.plan_counts.compute_plan_step_counts`;
  `services/gene_sets/frozen_step.py` is deleted for
  `veupathdb_mcp.wdk.gene_set_steps.frozen_step_id`; and
  `build_step_tree_from_graph` is a wrapper over
  `veupathdb_mcp.wdk.step_tree.build_wdk_step_tree` that re-raises
  `StrategyCompilationError`, so its two other callers and the three WDK rules it
  anchors keep the problem type they had. The library defaults name no product,
  so `platform/identity.py` holds the four names this deployment writes into a
  WDK account and every call site passes one. `cleanup_before_sweep` takes the
  run's `IntersectionConfig` instead of a site id, so a sweep that cleans up
  cannot forget the name its own run writes.

* **Every process that writes or matches a helper strategy reads one prefix.**
  The client's neutral default is `__internal__:`. `Settings` sets
  `veupathdb_internal_strategy_name_prefix` to `__pathfinder_internal__:`, the
  value this deployment has always written, and compose, the quadlets and
  `.env.example` pass `VEUPATHDB_INTERNAL_STRATEGY_NAME_PREFIX` to the api, the
  worker and the wdk-mcp container. A process left on the library default would
  recognise none of the helper strategies already in a researcher's account, so
  none would ever be cleaned up.

* **One refusal hierarchy, one handler.** `AppError` is
  `VEuPathDBError[ErrorCode]` and defines no `__init__` of its own, so the two
  exception handlers collapsed into `veupathdb_error_handler`, which maps any
  refusal by the code value the wire already names, and every
  `except (AppError, VEuPathDBError, ...)` tuple lost its first member.

* **The MCP server's own settings are named after the server.**
  `PATHFINDER_MCP_BASE_URL` and `PATHFINDER_MCP_SERVICE_TOKENS` are now
  `WDK_MCP_BASE_URL` and `WDK_MCP_SERVICE_TOKENS` in compose, the nightly
  workflow, the tests and this bundle. `PATHFINDER_WDK_MCP_URL` and
  `PATHFINDER_WDK_MCP_TOKEN` keep their names: those are what this deployment
  presents to a server it admits, not the server's own configuration.

* **The seed catalog reads the site registry.** `SEED_DATABASES` is the
  registry's 14 sites filtered to the ones a seed file exists for, so
  `get_seeds_for_site("trichdb")` stays refused with `SITE_NOT_FOUND` instead of
  raising `FileNotFoundError`, and a site added to the registry without a seed
  file cannot break `get_all_seeds()`. `ParamVocabSnapshot` is a projection of
  `veupathdb_mcp.catalog.ParameterInfo` rather than a hand copy of its fields,
  and the universal-search row appended to a ranked listing is the library's
  `UNIVERSAL_SEARCHES`.

* **The durable-progress e2e serves the thread's tail the way the host does, so
  the card's live progress is proven again.** The mocked tail answered every
  request with the task's gap alone. A client resuming a message a turn left
  open asks from a cursor before that message and ignores every chunk until its
  own `start` (PROTOCOL section 4), so both `data-task-progress` chunks reached
  no part: the card kept `0%` while the tail answered 200 twice, at `after=0`
  and at `after=1000000000002`. The mock now replays the suspending turn for a
  request under that turn's `done` cursor, serves the gap for the request at
  that cursor, and answers 204 after it.
  `features/conversation/runtime/durableTransport.test.ts` pins the same
  contract without a browser.

* **A thread opened through `POST /api/v1/conversations/open` names its
  assistant, so its first turn is answered.** The route created the row through
  `ConversationRepository.create`, which named no assistant, so the row took the
  runtime's mapped default `default`; the next `POST .../begin` resolved that id
  against a registry that installs `pathfinder` and `site_help` and answered 404
  `ASSISTANT_NOT_FOUND`, and no chat turn was ever deferred. `create` now takes a
  required `assistant_id` and every caller passes one: the strategy create and
  the WDK import pass `PATHFINDER_ASSISTANT_ID`, a duplicate copies its source's,
  and the open route resolves the body's optional `assistantId` through the
  registry, so an unknown id is refused where the thread is created instead of on
  its first turn. `resolve_turn_assistant` takes `conversation_id: UUID | None`
  for that caller, which reads no row. Pinned by
  `tests/integration/http/test_open_names_the_assistant.py` and
  `tests/unit/persistence/test_conversation_create_names_the_assistant.py`.

* **The live aiExpression checks discover their subject on the site instead of
  naming a gene per cache state, and plasmodb now answers `present`.** The site
  regenerates the cache, so a pinned id encodes yesterday's cache: PF3D7_1133400
  answered `expired` with 41 of 41 experiments on 2026-09-04 and
  `experiments_incomplete` with 0 of 41 today, while PF3D7_0709000 went the other
  way and now carries a whole summary. Each check reads the two recorded subjects
  and a page of the site's genes, takes the first gene in the state it needs, and
  skips with a sentence naming the site and that state when the page holds none.
  A `present` entry carries `resultStatus`, `expressionSummary` and
  `basedOnIncompleteData` and **no experiment counts**: `AiExpressionCache.readSummary`
  writes the counts and the `experimentStatus` map only on the branches that
  cannot answer a summary, so the counts a reader sees beside a summary are the
  client's zero defaults and mean nothing. Of 180 falciparum genes read on
  plasmodb, 2 answered `present`; a check that needs that state is one candidate
  page away from an honest skip.

* **The OpenAPI conformance lane fuzzes negative cases where the complement can
  be spelled, and only there.** A negative case draws from the complement of a
  barred keyword, and the canonical form declines the complement of the eleven
  branch parameter value union, whose `NumberRangeValue` and `DateRangeValue`
  give `min` and `max` two different types. The lane refused one operation per
  run and a different one each run. A predicate over the served spec now names
  the 15 operations of 94 that reach such a union and asks those for positive
  cases only; the other 79 keep negative coverage, and the draws are
  deterministic. Pinned by
  `tests/unit/transport/test_openapi_negation_support.py` and
  `test_openapi_schemathesis.py::test_negative_generation_stays_on_where_a_complement_exists`.

* **Seven modules left this tree for the two libraries that own them, and the
  runtime stopped defaulting to this product.** `veupathdb-py` v0.1.0a4 and
  `assistant-core` / `veupathdb-mcp-conformance` v0.2.0a4 carry the message-history
  processors, the per-provider model settings, the LLM capture wrapper, the
  input-screening scanners, the `GET /users/current` read and its typed user, the
  EDA validation predicates, the OpenTelemetry observer adapter, the WDK capture
  transport and the orphaned-step delete. Each call site imports the public name;
  no shim, no re-export. The behavioural tests moved with the code, and one test
  per item proves this application consumes the published surface: the four agents
  run the runtime's `HISTORY_PROCESSORS` in the runtime's order, the model catalog
  resolves through the runtime's settings builder, screening's refusal becomes a
  403 whose text names neither the scanner nor its score, and no module in this
  tree spells `/users/current` any more.

* **The application names itself; the runtime names nobody.**
  `DEFAULT_APPLICATION_ID` and `DEFAULT_ASSISTANT_ID` are `"default"` in the
  runtime, so `platform/identity.py` holds this deployment's two ids and the
  principal, the security fallback, the conversation response and the chat-turn
  job read them from there. Rows keep the application id they already carry, so
  no migration ships. A chat-turn payload now names its assistant: the dispatcher
  resolves one before it defers.

* **The six WDK and site-search instruments are `veupathdb.*`.** The adapter is
  the client's own optional extra (`veupathdb-py[otel]`), so it namespaces its
  numbers; the SigNoz pack, the dependency-reliability dashboard, the alert
  catalog and the query guide follow, histogram `.bucket` series included. The
  pipeline and SSE instruments keep their names.

* **`veupathdb-mcp` names its own source for the client, so the pin is written
  twice.** The MCP release pins `veupathdb-py` at an older tag by URL, and uv
  refuses two URLs for one package. `[tool.uv] override-dependencies` names the
  tag this project takes, so exactly one client is installed; the override and
  `[tool.uv.sources]` move together.

* **Nine runtime decisions and three platform gate sections moved to the
  platform bundle.** They are cited here, not linked: a page that describes only
  runtime behaviour has one home. `experimentId` is documented here instead,
  because the wire now ships an empty request-extension table.

## 2026-09-08

* **A sixth import contract forbids the private modules of the three installed
  distributions, and two dead modules left the tree.** The libraries join
  `pathfinder` in `root_packages`, because a forbidden contract cannot name a
  submodule of an external package; the fourteen `_*` modules are listed one by
  one, and three `ignore_imports` cover the tests that need a name a library does
  not publish yet; the 2026-09-09 release publishes two of the three, so one
  exception remains. `platform/notify_dispatcher.py` held an idle `LISTEN`
  connection in every API process for a route that no longer exists, and
  `transport/http/schemas/stream_events.py` declared an event union nothing
  emits, which the OpenAPI post-pass anchored into the spec and from there into
  the generated TypeScript that no page imported. Both are deleted, with the
  spec and `@pathfinder/shared` regenerated.

* **The four libraries moved to their released tags, and the browser tree moved
  to `ai` 7.** `veupathdb-py` v0.1.0a3, `veupathdb-mcp` v0.1.0a4, `assistant-core`
  and `veupathdb-mcp-conformance` v0.2.0a2, `@pathfinder/assistant-client`
  v0.2.0a2. LangGraph 1.1.6 to 1.2.11 and `langgraph-checkpoint-postgres` 3.1.1 to
  3.1.2, the versions the runtime package pins, so the app installs the checkpoint
  chain its serializer's gate runs. `ai` 6.0.154 to 7.0.87 with `@ai-sdk/react`
  4.0.90, `@assistant-ui/react` 0.15.17, `-ai-sdk` 1.4.8 and `-markdown` 0.14.13,
  which lifts the earlier hold at `-ai-sdk` 1.3.18; `@ai-sdk/provider` and
  `@ai-sdk/provider-utils` each resolve twice, because the `@assistant-ui`
  packages still ask for the line before;
  the root `resolutions` names the new `ai` pair and no longer pins
  `@assistant-ui/store`, whose 0.2.9 entry existed for the `tap*` exports the
  0.12 line read. It gains `assistant-cloud` at 0.1.42, because
  `@assistant-ui/ai-sdk` asks for `npm:*` while `@assistant-ui/react` asks for
  `^0.1.42`, and without the pin two copies resolve. One copy of `ai`,
  `@ai-sdk/react`, `@assistant-ui/core` and `@assistant-ui/store` resolves. The
  audit is down to the ESLint support notice: the `ai` advisory closes at
  6.0.250.

* **The snapshot route serves the runtime's own `EventsSnapshot`, and a suspended
  turn names the message it left open.** `fetch_snapshot_chunks` returns a model
  rather than a pair, so the local response model is gone and the route returns
  what the runtime built. The wire gains `openMessage` (`messageId` plus the
  exclusive `after` a tail replays the message from), which is how a client that
  lost its cursor resumes without tailing from `0`; `PROTOCOL.md` section 4 is the
  rule. `veupathdb_mcp.catalog` exports `has_contrast_sibling` publicly, so
  `frame_spec` no longer reaches into a private module.

* **The JavaScript tree moved to its newest compatible release, and the pin list
  shrank to what an advisory needs.** `next` 16.2.11 to 16.3.4 with
  `eslint-config-next` beside it, TypeScript 5.9.3 to 6.0.3 with typescript-eslint
  re-resolved to 8.69.0 (below 8.66 it refuses a TypeScript 6 checker), kubb 4.37.2
  to 4.39.3, prettier 3.8.1 to 3.9.6, jsdom 28 to 30, vitest 4.1.2 to 4.1.11, zod
  4.3.6 to 4.5.4, and the OpenTelemetry web packages to 2.11.0 and 0.222.0. Root
  `resolutions` no longer names `nanoid`, `protobufjs`, `sharp` or
  `@opentelemetry/core`: the nanoid pin was unqualified and forced nanoid 3 onto
  three packages that declare `^5.1.7`, `protobufjs` leaves the tree with
  `@opentelemetry/otlp-transformer@0.222.0`, `sharp` at 0.35.0 no longer satisfies
  what `next` 16.3.4 asks for, and `@opentelemetry/core` at 2.10.0 would downgrade
  the 0.222 exporters. `postcss` stays, because `next` pins it exactly and only an
  unqualified resolution can raise it. `yarn npm audit --all --recursive` now
  reports two advisories where it reported 91: the ESLint support notice, which
  `apps/web` cannot close yet, and GHSA-866g-f22w-33x8 on
  `@ai-sdk/provider-utils@4.0.23`, which the exact `ai` and `@ai-sdk/react`
  resolutions hold in place and which closes when those pins move to `ai`
  6.0.250 or newer. Deleting a pin can also un-dedupe a tree, so two packages
  needed re-resolving once the pins left:
  `@opentelemetry/instrumentation-user-interaction` asks for `@opentelemetry/core`
  and `@opentelemetry/sdk-trace-web` at `^2.0.0`, which the deleted pin had been
  collapsing onto one copy, and `vite` was still frozen at 8.0.3 under vitest.

* **An exact pin on `ai` has to name `@ai-sdk/react` too.** `@ai-sdk/react@3.0.156`
  declares `ai` at the exact version 6.0.154; the two are one release. A resolution
  on `ai` alone therefore forces 6.0.154 underneath any newer `@ai-sdk/react` that
  a dependent pulls in, which is the same silent downgrade the removed OpenTelemetry
  pin caused. Both are resolutions now and the lock holds one copy of each.
  `@assistant-ui/react-ai-sdk` stays at 1.3.18 for the same reason: from 1.3.19 it
  requires `ai` and `@ai-sdk/react` ranges the pinned pair cannot meet, and taking
  it produced a second `@ai-sdk/react` in the tree.

* **`@assistant-ui/store` is pinned to 0.2.9, because the 0.12 line reads names the
  store renamed.** `@assistant-ui/react@0.12.28` and `@assistant-ui/core@0.1.17`
  import `tapClientLookup` and `tapClientResource`. The store renamed every `tap*`
  export to `use*` at 0.2.14, re-added the aliases at 0.2.20 and dropped them again
  at 0.2.21, so the newest release satisfying the declared `^0.2.9` breaks fifteen
  test files at import. 0.2.9 is the store that shipped with core 0.1.17. The pin
  lifts with assistant-ui 0.15, which is reachable only through
  `@assistant-ui/react-ai-sdk` 1.4.1 and `ai` 7.

* **The two legacy assistant-ui context hooks are gone from the app.**
  `useAssistantRuntime` and `useEditComposer` are removed in assistant-ui 0.15;
  their replacements exist already at 0.12, so the app now reads
  `useAui().thread().append(...)` and
  `useAuiState((s) => s.message.composer.text)`. Pinned by a ChatThread test that
  asserts a pending submission reaches the thread and is cleared, and by an
  EditComposerSend test that drives the branch and revert from the composer text.

* **The results table runs on TanStack Table 9.** v9 makes features opt-in, so the
  table registers `columnVisibilityFeature`, `rowSortingFeature`,
  `rowPaginationFeature` and `rowExpandingFeature` with their row-model factories in
  one `tableFeatures()` call, `useReactTable` became `useTable`, the core row model
  is automatic, and `table.getState()` became `table.state`. The feature set is one
  module so every component types its table, row, header and column definitions
  against the same `typeof features`. The two `"use no memo"` directives the React
  Compiler needed under v8 are gone, because v9's `useTable` returns a fresh
  React-facing table reference on every state change, so a component that receives
  the table re-reads its state. A component that receives only a row, a cell, a
  column or a header does not: the table keeps those objects across a state change,
  and the React Compiler caches a read such as `row.getIsExpanded()` on that
  identity. State a nested component needs therefore arrives as a prop from the
  component that holds the table: `RecordRow` takes the expanded flag and the
  visible cells from `ResultsTableBody`. Pinned by a test that compiles both files
  with `babel-plugin-react-compiler` and drives the compiled output.

* **A snapshot can no longer rewind a thread's resume point.** The app wrote the
  snapshot's cursor to the store unconditionally, while the client library's own
  `AssistantClient.snapshot()` only advances it, and the streaming transport built a
  second cursor store of its own. A snapshot that answered with a cursor lower than
  the stream had already recorded moved the resume point backwards and the tail
  replayed frames the client held. One store is now created once and handed to both
  the `AssistantClient` the snapshot query reads through and the
  `DurableChatTransport`. The library reads through a fetch the app supplies, so a
  refusal still reaches the reader as the app's own `APIError` carrying the sentence
  the server offered, and the 404 that means "no event log" still reads as an empty
  transcript. Pinned by three tests: a snapshot reporting cursor 7 against a stored
  42 leaves 42, a transport built by the shared factory resumes at `after=42`, and a
  500 surfaces the server's own message.

* **Eight upgrades are held, each with the condition that lifts it.** TypeScript 7.0.2
  ships no JavaScript compiler API, typescript-eslint caps below 6.1 and `next` reads
  `typescript/lib/typescript.js`; it lifts when those three change. ESLint 10 waits
  for `eslint-plugin-import`, `eslint-plugin-react` and `eslint-plugin-jsx-a11y` to
  declare an ESLint 10 peer, which is why the support-policy advisory stays open in
  `apps/web`. Vitest 5 changes the mock-clearing defaults and needs its own change.
  Kubb 5 is a restructure with no `@kubb/plugin-oas` at all, replaced by
  `@kubb/adapter-oas`, so it needs a deliberate codegen migration. Stryker 10 moves
  the instrumenter to Babel 8 and changes the mutant set, so the mutation score
  would not compare. Motion 13 waits for `reaviz` to widen its `motion ^12.40.0`
  dependency, because two motion majors in one tree are two animation contexts.
  Postcss 8.5.28 is younger than the seven days the install gate allows, so the
  resolution stays at 8.5.26 until 2026-09-10. `ai` 7 is the backlog item that
  already exists.

* **A count in an exhibit table shows the genes behind it.** A control test read
  "2 of 3" with no way to see which two. Every control-set count is now a
  `CountOfIds` control: hover or focus lists the ids it stands for, a click
  copies them, and the card says how many of the count are shown, because WDK
  samples a long list. A count with no sampled ids stays a plain number, which
  is every negative set's own size: the ids a target correctly left out are
  never sampled.
* **A control test on a search leaves the same table as one on a step.**
  `run_control_tests_on_search` wrote only a summary line, so a test the model
  ran before it built a strategy produced no exhibit. It now emits
  `data-control-test-results` on its return metadata, with `task_id` empty
  because no worker task carried it.
* **The tested step is named once.** An unnamed step read "step 440299573 (step
  440299573)": the header appended the step id to a label that had fallen back
  to the step id. One label now decides the whole line.
* **A search's published names have one reader.**
  `services/experiment/published_names.py` reads what WDK calls a search and
  each of its parameters, and refuses a url segment as a label, so the catalog's
  own fallback cannot leak one. The worker and the search-level tool both use
  it. Pinned by `test_published_names.py`.
* **A finished task row points at no exhibit.** The table it produced reads
  directly under the row, so `see Table N` in the thread was a link to what the
  reader was already looking at. The right rail keeps its jump, because a task
  listed there is not beside its table.

* **The api's Python dependencies moved to their current releases, and the
  library pins did not.** pydantic-ai 2.41, fastapi 0.141, pydantic 2.13.5,
  openai 3, anthropic 1, OpenTelemetry 1.44 with its 0.65b0 instrumentation,
  langfuse 4.15, procrastinate 3.9, mypy 2.3.1 and ruff 0.16.6 lead the move;
  `langgraph` and `langgraph-checkpoint-postgres` stay `==` pinned at the
  versions `assistant-core` names, `mcp` stays below 2 and `fastmcp-slim` below
  4, and the four repository sources keep their tags. Three moves ask for code.
  `Agent._instructions` now holds `SourcedInstruction`, so
  `tests/_support/instructions.py` reads the pinned text or the renderer name
  once for the three suites that assert an instruction order. `include_router`
  is lazy, so a router holds include nodes and not routes:
  `tests/_support/routes.py` walks `iter_route_contexts` and reads
  `ctx.dependant`, which carries the dependencies an include applies, so the
  gate tables still report the 34 gated routes that `original_route.dependant`
  would under-report as 23. The model providers speak `httpx2`, so
  `_instrument_http_clients` instruments both httpx distributions and a
  provider call still leaves a span. `testcontainers.postgres` became
  `testcontainers.community.postgres`. ruff 0.16 promotes ISC004, so every
  wrapped string inside a list literal is parenthesised and stays one string,
  and `ruff format` now formats the Python blocks in the Markdown under
  `apps/api`, which is where the gate runs. The uv that the image and CI
  install is pinned at 0.12.10 in both places. The
  published spec gains one field, `ReasoningUIPart.id`, which pydantic-ai 2.41
  declares.

## 2026-09-07

* **An exhibit table reads like a table in a paper.** The control-test exhibit
  drew four numbers in monospaced flex rows, so a reader saw
  `boolean_question_TranscriptRecordClasses_TranscriptRecordClass`, no gene id
  and no criterion. `ExhibitTable` now draws a real `<table>`, centred, ruled
  above the head, under it and under the body, numbers in the body font on one
  digit width, and the monospaced face kept for gene ids alone; its notes read
  under the bottom rule. `data-control-test-results` carries what a reader
  needs: `target_label` (what WDK calls the tested step, never a search url
  segment), `target_parameters` (each criterion under WDK's own display name),
  and per control set the ids behind the counts (`hit_ids`, `missed_ids`). The
  worker resolves those names once, from `find_step` and the search's published
  parameters, and reports them beside the library's numbers; both degrade to
  empty when WDK refuses the read. `data-scored-comparison` and
  `data-variant-comparison` draw the same table, with their failures, control
  membership, unique ids and pairwise overlaps as table notes. Pinned by
  `ExhibitTable.test.tsx`, `DataControlTestResults.test.tsx`,
  `DataScoredComparison.test.tsx`, `DataVariantComparison.test.tsx`,
  `test_experiment.py` and `test_control_tests_impl.py`.
* **A waiting turn says which step it is on.** "Preparing context" covered the
  whole opening of a turn, so a slow memory read looked like a hang. The runner
  opens with "Starting the turn" and the lead node names "Recalling earlier
  work" and "Reading the thread" before the model is waited on. Pinned by
  `test_turn_status_names_the_step.py`.
* **The MCP image's release is committed, not configured.** `docker-compose.yml` named the image's revision through a
  required `WDK_MCP_REV`, so the served tools and the imported ones could be different releases and a fresh clone
  refused to start until someone set it. The build context now carries the tag beside the Python pin, so one commit
  moves both; the variable is gone from the env templates, the CI e2e job and the docs.
* **A dropped connection to the OAuth server no longer fails a turn.** `veupathdb-py` 0.1.0a2 retries the JWKS read,
  serves the last key the server published while it cannot be read, holds a key for an hour instead of two minutes,
  and names the exception class when a failure carries no message. `veupathdb-mcp` 0.1.0a3 takes that client.
* **An enrichment exhibit names the call it answers**, so its task row reads the summary the tool already wrote.



* **The chat's experiment results are numbered exhibits, and each one can be
  cited.** Tables now carry a counter of their own, so `Figure 1` and `Table 1`
  both exist: `tableNumbers.ts` numbers the control-test part,
  `data-scored-comparison`, `data-variant-comparison` and
  `data-enrichment-results` by the payload the thread holds, so two equal
  payloads take two numbers and a number does not move while the turn streams.
  The plots keep `figureNumberFor` and their numbers. `Figure` replaced
  `numbered` and `figureNumber` with one `exhibit` identity (`figure` or
  `table`, plus the number), renders `id="table-2"` / `id="figure-3"` on the
  `<figure>`, and puts `ExhibitCitation` in the title row, which copies the
  conversation url with that fragment. A control test emits its numbers as
  `data-control-test-results` beside its summary line. A finished task row reads
  the tool's own line in place of "Completed"; `taskResultHref` and its
  message-anchor resolution are gone, because they pointed at the message the
  row already sat in. The scroll-to-bottom control moved out of the scrolling
  viewport onto a
  zero-height rail above the composer. Pinned by `test_experiment.py`,
  `test_control_tests_impl.py`, `test_stream_part_registry.py`,
  `tableNumbers.test.ts`, `Figure.test.tsx`, `DataControlTestResults.test.tsx`,
  `taskExhibit.test.ts`, `TaskRow.test.tsx`, `conversation.test.tsx` and
  `ChatThread.test.tsx`.

* **A site that is down is down on its own.** The portal stopped answering
  `record-types` (no HTTP status in 60 s, against 0.77 s on plasmodb), the api
  preloaded every catalog before `/health/ready` would pass, and one dead site
  made the container unhealthy, kept its compose dependents down and killed the
  e2e job twice. Readiness is now the process: every fixed subsystem plus at
  least one loaded catalog, with `degraded` naming the sites whose catalog did
  not load, on `/health/ready` and `/health/system`. The warm-up loads the sites
  concurrently, each inside `SITE_PRELOAD_TIMEOUT_SECONDS` (30), records the
  error class alone, and a lifespan task retries the degraded sites every
  `SITE_RETRY_INTERVAL_SECONDS` (60) under the same budget. A degraded site is
  refused before any catalog or WDK call by one dependency,
  `require_available_site` (503 `SITE_UNAVAILABLE`), with the chat body read by
  its own sibling; `GET /api/v1/sites` carries `available` and
  `unavailableReason`; the site menu keeps the site selectable and marks it
  "Not responding", refetching every 60 s. Decision:
  `decisions/a-site-that-is-down-is-down-on-its-own.md`. Pinned by
  `tests/unit/platform/test_site_catalogs.py`,
  `tests/unit/transport/test_site_availability.py`,
  `tests/unit/transport/test_site_gate_route_table.py`, the health cases in
  `tests/integration/transport/test_system_ready.py`,
  `AppNavRail.test.tsx` and `e2e/feature/site-availability.spec.ts`. The new
  tests also caught three defects, fixed in the same change: `/health/ready`
  serialized its 503 body without `by_alias`, so `notReady` was `not_ready`
  there and the body did not match the published schema; the schemathesis
  conformance app marked the fixed subsystems ready and no catalog, so it read
  503; and the warm-up preloaded the portal first, which spent every other
  site's budget because one catalog builds at a time (components now sort
  first, as `preload_all` did). Measured with the portal down and an empty
  snapshot volume: `api Healthy` 8 s after the preload starts against 63 s
  before the sort, and never before this batch.
* **The entry flow does not land on a degraded site.** `localhost:3000/`
  redirected to the portal unconditionally, so opening the app during a portal
  outage landed on the one site that could not answer. Every site-less route -
  `/`, `/conversation`, `/workbench` and `/workbench/[id]` - now reads
  `GET /api/v1/sites` on the server and redirects to the portal's own URL when
  it answers, else to the first site in the list's order that answers; when the
  request fails or no site answers it renders the startup screen instead of
  redirecting. A URL that names a degraded site renders `SiteUnavailableNotice`
  (the display name, the error class, a link to every site that answers) in the
  routed content area, inside the app shell, and the 60 s sites refetch brings
  the app back without a reload; a refused sign-in shows the same notice
  inline. Pinned by `lib/sites/entrySite.test.ts`, `app/page.test.tsx`,
  `app/siteLessRedirects.test.tsx`,
  `app/components/SiteAvailabilityGate.test.tsx`,
  `features/sites/components/SiteUnavailableNotice.test.tsx`, the root-visit
  case in `e2e/feature/site-availability.spec.ts`, and the store case in
  `app/[siteId]/(app)/layout.test.tsx`.
* **A dead portal no longer costs a healthy site six minutes, and a degraded
  site keeps its shell.** Verification of the degraded-sites batch measured a
  signed-in researcher on PlasmoDB getting `502 WDK_ERROR` after 374.41 s from
  `GET /api/v1/eda/studies?siteId=plasmodb` while `veupathdb.org` answered
  nothing: `require_session_matches_wdk_identity` read `/users/current` on the
  configured default site for all 34 identity-gated routes, and
  `fetch_wdk_user` did not catch `VEuPathDBError`. `GET /users/current` answers
  the same WDK user id (`1216062453`, `isGuest: false`) on plasmodb, toxodb and
  the portal, so the identity check now takes the site the request names,
  `identity_site` hands the read to the first loaded site when that one is
  degraded, `require_registered_wdk_identity` refuses a named degraded site
  before the read, and the except tuple carries `VEuPathDBError`. Measured on
  the same outage after the change: 1.567 s cold and 0.017 s warm on that
  route, and `POST /api/v1/gene-sets` (which names no site, so its default is
  the dead portal) `201` in 0.837 s. The same verification found the
  availability gate above the nav rail, which made
  `AppNavRail`'s degraded-trigger branch unreachable; the gate now renders
  inside both app shells around the routed content, so the rail, its marker,
  the conversations list and the workbench's gene sets stay reachable on a
  degraded site while the notice takes the content area, and the sign-in prompt
  is the one thing it still replaces. `POST /api/v1/experiments/seed` spells
  its site `siteId` like every other route. Pinned by
  `tests/unit/services/test_wdk_identity_site.py`,
  `tests/unit/transport/test_auth_status_reads_a_loaded_site.py`, the closure
  and naming cases in `tests/unit/transport/test_site_gate_route_table.py`,
  `lib/sites/availability.test.ts`, `app/siteLessRedirects.test.tsx`, and the
  degraded-shell cases in `app/[siteId]/(app)/layout.test.tsx` and
  `app/[siteId]/workbench/layout.test.tsx`.
* **A sign-in to a site that does not answer is a 503, not a 500.**
  `password_login` posts with no error mapping, so with the portal down
  `POST /api/v1/veupathdb/auth/login` (its `siteId` defaults to `veupathdb`)
  raised `httpx.ReadTimeout` out of the route and the browser got an opaque
  500 after the whole read timeout. The route now answers the same 503
  `SITE_UNAVAILABLE` the degraded-site gate answers, and the refusal reads
  "<site> is not responding (<error class>)" for both situations. The
  schemathesis conformance fixture refuses the fuzzer's credentials locally,
  so a VEuPathDB outage no longer turns that check red.
  Pinned by `tests/unit/transport/test_login_refuses_an_unreachable_site.py`.

## 2026-09-06

* **Deleting a conversation stops its running turn first, or refuses.** The first CI run of the org repository
  showed the worker failing three turns with a foreign-key violation on `conversation_events`: each spec's
  cleanup had deleted the conversation while its turn was still writing. `ConversationService.delete` now calls
  `stop_turn_before_delete`, which stops the turn and waits for the worker the way the bulk user-data wipe already
  did, and answers 409 `SESSION_CONFLICT` (`TurnStillRunningError`) when the worker does not close inside the
  window. Pinned by `tests/unit/services/conversations/test_delete_waits_for_the_turn.py`.
* **The e2e suite signs in from the account's email and password when no token is exported.** The org
  repository's CI had no `WDK_TEST_TOKEN`, so 103 specs failed with the fixture's refusal while the stack itself
  was healthy. `e2e/global-setup.ts` posts the login once and hands the `Authorization` cookie to every worker;
  `ci.yml` passes `WDK_TEST_EMAIL` and `WDK_TEST_PASSWORD` as repository secrets, and the failed run's
  `test-results` are uploaded as an artifact. Proved on the mock stack with the token unset: 3 passed.
* **The Security workflow is honest on a private repository.** CodeQL and the SARIF upload need a public
  repository or Advanced Security, so both are gated on visibility and the private path fails the job on
  CRITICAL or HIGH Trivy findings. The first such run listed 28 in `yarn.lock`; `next` moved to 16.2.6 and
  `nanoid`, `postcss`, `protobufjs` and `sharp` are pinned through unqualified Yarn `resolutions`, the only
  form that overrides an exact transitive pin.

* **The api's live lane keeps its catalog snapshots out of the tree, and asserts the client's refusal.**
  `tests/conftest.py` sets `CATALOG_CACHE_DIR` to a temporary directory for the session, because
  the MCP distribution's default is the cwd-relative `data/catalogs` and a live discovery wrote a
  7.7 MB `apps/api/data/catalogs/plasmodb.json` into the source tree under no ignore rule; the
  unit test `test_catalog_cache_dir_is_outside_the_tree.py` holds the invariant. The two live tests
  that expected PathFinder's `AppError` from `veupathdb_mcp` functions now expect `WDKError` with
  the status WDK returned (404 for an unknown search, 422 for a bad parameter): the MCP
  distribution cannot raise an exception of this app, so the nightly lane failed on both since
  the MCP split.

* **The three folders left the repository, so the four repositories are the cut-over.**
  `veupathdb-py/`, `veupathdb-mcp/` and `assistant-platform/` are deleted here; the
  repositories `VEuPathDB/ai-veupathdb-client`, `VEuPathDB/ai-wdk-mcp` and
  `VEuPathDB/ai-assistant-platform` are the only copy. The platform pins moved to the
  commit that carries `assistant_core/PROTOCOL.md`, so the six `test_request_body.py`
  cases that read the document from a sibling folder are green from the installed
  distribution and the api unit suite is 3236 passed, 0 failed. Every path that named a
  folder was already gone; what remained and stayed is the bundle's citation form
  (the `assistant-platform` prefix over a path inside that repository), the dated
  entries above, and the
  two `subdirectory` values in `[tool.uv.sources]`, which name a path inside the platform
  repository and not a folder here.

  Four claims the split had invalidated were corrected with it: `apps/web` compiles the
  packed `dist` and holds no `tsconfig` path or vitest alias into the client's source
  (`assistant-platform: docs/knowledge/decisions/the-client-is-a-package-with-three-rings.md`, `conventions/verification-gates.md`);
  `PROTOCOL.md` is package data of the runtime and not the grouping's root
  (`the-assistant-platform-is-a-grouping.md`); the three distributions are consumed by
  URL and not as editable path dependencies (the three distribution decisions, the last
  of which gained the `Publishing` section the other two already had); and
  `[tool.uv] override-dependencies` no longer exists, because the pinned MCP commit names
  the client by the same URL and the same `rev`. `docs/DEVELOPMENT.md` said seven layer
  contracts where `lint-imports` reports five, and put a sibling clone inside this
  repository. The root README named `WDK_MCP_REV` in neither its fail-closed list nor
  its e2e recipe, and `docker-compose.yml` demands it with `${WDK_MCP_REV:?}`, so both
  documented bring-ups aborted before they built anything; both name it now.

  The e2e CI job prints the stack's logs on failure per service (`--no-color api worker
  web db`) over the same overlay set its bring-up names, because the first full-stack run
  reported `container api exited (3)` and nothing else.

* **PathFinder consumes the three libraries by URL at a commit, and copies none of them.**
  `apps/api/pyproject.toml` names `veupathdb-py`, `veupathdb-mcp`, `assistant-core` and
  `veupathdb-mcp-conformance` by repository and a 40-character `rev`; `apps/web/package.json`
  names `@pathfinder/assistant-client` by repository, workspace and commit, and compiles the
  packed `dist` instead of the folder's source, so the three `tsconfig` paths and the two
  vitest aliases are gone; `docker-compose.yml` builds `wdk-mcp` from
  `https://github.com/VEuPathDB/ai-wdk-mcp.git#${WDK_MCP_REV:?}`; both Dockerfiles install
  `git` and copy no sibling. The five library lanes left `ci.yml` and the seventeen
  library hooks left `.pre-commit-config.yaml`: each repository runs its own. Recorded in
  `decisions/the-libraries-are-consumed-by-git-url.md`.

  Two measurements changed the plan. uv reads `tool.uv.sources` out of a git dependency that
  is a source tree, so the MCP repository's `path = "../veupathdb-py"` row reached the
  resolver and `uv lock` failed with `has no subdirectory ../veupathdb-py`, on uv 0.8.13 and
  on 0.12.10 alike; `[tool.uv] override-dependencies` states the app's client pin until the
  re-exported MCP commit names the URL itself. And `PROTOCOL.md` sat at the platform
  repository root, outside every distribution, so six `test_request_body.py` cases read
  `.venv/PROTOCOL.md` and failed; the document is now
  `packages/assistant-core/src/assistant_core/PROTOCOL.md`, which a source checkout, an
  editable install and a wheel resolve identically, pinned by a new `tests/packaging`
  wheel test.

  `scripts/check-wdk-rules.mjs` reads an `- anchor:` or `- status:` naming one of the three
  repositories as a citation rather than resolving it, and reports how many rules are
  anchored that way (5 of 8). The catalog snapshot directory is a setting
  (`CATALOG_CACHE_DIR`), because the api image no longer carries the MCP repository's `data`
  and an installed package cannot resolve a writable directory from its own location.

## 2026-09-05

* **An enrichment over a result of several organisms is refused.** Measured on toxodb.org: the
  journey's unfiltered `invasion` search returns 10 genes of 7 organisms, and the WDK enrichment
  form for that step offers an `organism` vocabulary of those 7 with `Eimeria falciformis Bayer
  Haberkorn 1970` as its default, so the workbench tested 1 gene and reported "0 significant terms"
  over "10 genes analyzed". `EnrichmentService._execute_analysis` now raises
  `AmbiguousBackgroundError` naming every organism when the form offers several and no
  `BackgroundSource` organism was given; the journey seed narrows each site's search to its
  organism. Recorded in `decisions/an-enrichment-over-several-organisms-is-refused.md`. In the same
  verification pass: the eslint override for `react-hooks/incompatible-library` now names
  `features/workbench/analysis/components/ResultsTable/**` (the move left the old path);
  `describe_eda_study` builds `EdaStudyDescription` with `model_dump(exclude={"variables"})` so
  pyright 1.1.411 reports 0 errors like 1.1.408; the durable enrichment integration test runs the
  real facade and the real `EnrichmentService` over recorded WDK step answers; every first-party
  `import ... as` is gone (119 across four trees, 34 third-party conflicts kept).

* **The two folders became pushable: the bundles cite each other, the platform is its own Yarn
  project, the library's fixtures ship in its wheel, a catalog loads without its vector index, and
  every unit-test directory names a package that exists.** Copied outside this checkout,
  `veupathdb-py/`'s own `check-knowledge` step exited 1 with **45** unresolved links into
  `docs/knowledge/{decisions,wdk/pathfinder}`. `eda/pathfinder-architecture-fit.md` and
  `eda/pathfinder-integration-concept.md` were PathFinder proposals, not EDA facts, and are back at
  `docs/knowledge/eda/`; the remaining 30 links, and the 98 in the other direction, are backticked
  citations of the sibling repository path, because the two repositories are never checked out
  together. The outside copy now reports `41 files conform to OKF v0.2 (0 violations)`. Recorded as
  [the knowledge bundles cite each other](decisions/the-knowledge-bundles-cite-each-other-they-do-not-link.md).
  `assistant-platform/` is its own Yarn project - `package.json`, `.yarnrc.yml`, `yarn.lock`,
  `.github/workflows/ci.yml` with the three lanes and `.pre-commit-config.yaml` with their hooks -
  and the monorepo root's `workspaces` no longer names the TypeScript client; `apps/web` reaches it
  through `portal:../../assistant-platform/packages/assistant-client-ts`. With the folder's own lock
  the client's 262 conformance cases pass at `ai` 6.0.154, the version `@ai-sdk/react@3.0.156` pins;
  at 6.0.271 two of them fail, because `ai` 6.0.250 made `resumeStream` a fresh response instead of a
  continuation of the held assistant message, which is the opposite of what section 6.1 of
  `PROTOCOL.md` requires of a turn suspended on a durable task. The pin carries that reason. The
  recorded WDK and EDA stores
  moved from `veupathdb-py/tests/fixtures/` to `src/veupathdb/testing/fixtures/{wdk,eda}/`, read
  through `importlib.resources`, and a wheel test installs the built wheel into a fresh venv and
  reads one fixture of each: `unzip -l dist/*.whl | grep -c fixtures` went from 3 to 76.
  `SearchCatalog` now collects its semantic index and starts the sync beside the load instead of
  awaiting it, and `record_manager` opens every session through one boundary that turns a driver
  refusal into `IndexStoreUnavailableError` under the shared `SemanticIndexUnavailableError`; an
  `asyncpg` `PostgresError` is a relation of neither `SQLAlchemyError` nor `OSError`, which is how a
  Postgres refusal used to reach a gene search. The `apps/api` live lane is **27 passed** with
  `DATABASE_URL` unset and no `EMBEDDING_INDEX_SYNC_ENABLED=false`. Seven `apps/api` unit-test
  directories that mirrored no `src` package are gone: two modules that name only `veupathdb_mcp`
  are that folder's suite (35 cases), one that names only `veupathdb.domain.eda_study` is the
  library's (9 cases), and the rest sit under the mirror of what they test, held by
  `tests/unit/test_tests_mirror_the_source.py`. ToxoDB's primary button was 3.84:1 against white in
  its `hover:bg-primary/90` state; `clampLightnessForForeground` now measures that composite, so all
  fifteen sites clear 4.5 in both states on both grounds.

* **The workbench became one module on both sides, and each boundary became a gate.**
  `features/analysis` (78 files) is `features/workbench/analysis`, so the
  `["workbench", new Set(["analysis"])]` exception row is gone and the 8 import lines
  that named `@/features/analysis` name the workbench. `check-boundaries.mjs` gained
  `FEATURE_ENTRYPOINTS` and rule 6: a feature that publishes entry paths is reachable
  through them and nothing else, so `"workbench"` left the `conversation` exception row
  too - `conversation -> @/features/workbench/api/geneSets` passes on the path and
  `conversation -> @/features/workbench/components/panels/BatchPanel` fails, where the
  old exception admitted `@/features/analysis/components/ResultsTable`. The
  checker is now a `checkSource` function with 12 `node --test` cases, run by pre-commit
  and CI beside the check. Two e2e specs stopped being cross-feature and moved to
  `e2e/feature/`. On the backend, the 24 lines in 12 files under `ai/` and `jobs/` that
  named a workbench service are 15 type imports and 9 facade imports:
  `services/workbench/{gene_sets,experiments,control_sets,comparisons,optimization}.py`
  hold 15 functions with bodies, and import-linter contract 8 (the fifth in the file,
  direct-only) forbids the six modules whose behaviour they own. **Five contracts.**
  `SweepTarget` and `SweepControls` moved to `parameter_optimization/config.py` so the
  worker impl can name them without naming the forbidden module. The measured answer to
  "should the workbench be its own repository" is no: a repository when a second consumer
  or a second container exists, a module with two gates until then.

* **The MCP server is a distribution, the three platform packages are a grouping, and a site's
  gene search stopped answering with other sites' genes.** `pathfinder/{mcp, services/catalog,
  services/wdk, services/gene_lookup, services/control_*, services/tool_payloads,
  integrations/embeddings}` are `veupathdb-mcp/` (90 modules), imported as `veupathdb_mcp`, with
  its own pyproject, lock, README, Dockerfile, alembic chain and CI lane; 565 import lines were
  rewritten across 267 files. `apps/api` installs it as an editable path dependency and calls it
  in process (132 production edges), so import-linter contract 7 is deleted and the empty
  `pathfinder/integrations/` package with it: **four contracts remain**. The unit's boundary is an
  installation fact - `rm -rf .venv && uv sync --frozen && uv run pytest tests/unit` resolves a
  lock naming no application, and 710 tests pass with `pathfinder` unimportable. The embedding
  migration moved to a chain of its own recorded in `alembic_version_veupathdb_mcp`; both chains
  were driven up, down and up again on clean `pgvector/pgvector:pg16` databases, together and
  apart, and the two table dumps are identical across the trip. `packages/{assistant-core,
  assistant-client-ts, mcp-conformance}` and `PROTOCOL.md` moved under `assistant-platform/` with
  **zero import rewrites** - only paths: two `uv.sources` rows, five `COPY` lines, the yarn
  workspace, eight pre-commit `files:` patterns, twenty CI working directories, `pyrightconfig`,
  two vitest configs and the client's `sync:protocol`. The `wdk-mcp` image is now built from
  `veupathdb-mcp/Dockerfile` and carries no PIGuard model and no `pathfinder`. **The site gene
  search fix**: one SOLR index serves every VEuPathDB site and the deployed service does not
  filter gene documents by `restrictToProject`, so plasmodb's `kinase` query answered
  `totalCount 1175519` led by Cordyceps, Aspergillus, Blumeria and Trypanosoma genes.
  `list_organisms` now reads the leaves of the site's own `SequencesByTaxon` organism parameter
  (64 on plasmodb) rather than site-search's `organismCounts` (831, every organism in the index),
  and both request forms send it: the same query answers `totalCount 17516` over Plasmodium
  genes. The two served tests read `veupathdb_mcp.__version__` instead of PathFinder's.

* **The client library became a distribution.** `pathfinder/{veupathdb, integrations/veupathdb, integrations/eda}`, the WDK-shaped half of
  `domain/` and the three WDK/EDA devtools are `veupathdb-py/`, imported as `veupathdb` and
  consumed by `apps/api` as an editable path dependency. The WDK and EDA knowledge bundles
  moved with the code; `wdk/pathfinder/` stayed and now holds the eight `WDK-MAP` rules.
  Import-linter contracts 1 and 4 are deleted. See
  [the client library is a distribution](decisions/the-client-library-is-a-distribution.md).

* **A gene set can be published to the researcher's VEuPathDB workspace.**
  VDI accepts PathFinder's own registered token: `GET https://plasmodb.org/vdi/datasets`
  answers 200 for `Authorization: Bearer <token>`, for the `Authorization` cookie and for
  `?access_token=`, and 401 with no credential, with a raw header and with `Auth-Key`.
  One probe `genelist` of five genes reached `install: complete` on PlasmoDB 7.6 s after
  the 202 and was deleted. `integrations/veupathdb/vdi/` (client + wire models) now calls
  five endpoints, `services/gene_sets/vdi.py` publishes and reads status, `gene_sets` gains
  a nullable `vdi_id` (alembic 2026_09_05_0001), and the workbench header carries one
  confirm-first button. Replacing the `gene_sets` table with VDI, feeding a `VdiId` into a
  WDK `DatasetParam` and giving an agent the action were all rejected; see the decision and
  `wdk/rest/vdi-surface.md`.

* **PathFinder now reads VEuPathDB's own per-gene AI expression summary instead
  of having none: `get_ai_expression_summary` is an agent tool and an MCP tool
  over the `aiExpression` WDK reporter, and it can never ask the site to
  generate one.** The 2026-09-04 survey could not settle whether the reporter
  answers a service credential, because every probe hit the API-key 401. It
  does. Measured on plasmodb on 2026-09-04: anonymous is **401** `Valid API Key
  required for this endpoint`, and the deployment's service token and a
  registered user's token both answer **200**, whether the token travels as a
  bearer header or as the `Authorization` cookie the client already sets. So the
  call is a user-independent read and needs no login gate. Two other facts moved
  with it. `primaryKeys` needs both primary key columns - `"PF3D7_1133400"`
  alone is a 422 naming `[ source_id, project_id ]`, `"PF3D7_1133400,PlasmoDB"`
  is a 200 - so the service appends the site's configured `project_id`. And a
  cache miss is a 200 carrying a status, never a 404: PF3D7_1133400 answered
  `"expired"` with 41 of 41 experiments cached and PF3D7_0709000 answered
  `"experiments_incomplete"` with 0 of 41, and neither carried an
  `expressionSummary`. No site answered `"present"` for any of the 40 genes
  probed across seven sites, so the generated-summary shape is read from
  `aiExpressionTypes.ts` and `Summarizer.java`'s response schema rather than
  from a live body; the client models it and a unit test pins it.
  **`populateIfNotPresent` is `Literal[False]`**, because `true` runs Claude over
  every experiment of the gene and a deployment-wide `DailyCostMonitor` answers
  503 for everyone until midnight once the day's dollar cap is passed - the new
  WDK-ANS-009 (`veupathdb-py: docs/knowledge/wdk/rules/searches-and-answers.md`), pinned to
  `SingleGeneAiExpressionReporter.java` and `DailyCostMonitor.java`. The reporter
  row in the endpoint surface (`veupathdb-py: docs/knowledge/wdk/rest/endpoint-surface.md`) is no longer
  `unused`. Two fixtures record the two miss shapes, and the live lane checks
  both plus the 422.

* **The embedding index left the assistant runtime: the last 9 upward edges out
  of the future `veupathdb-mcp` module set became 0, and the served closure now
  names no `assistant_core` module at all (133 modules, 17869 -> 15027 -> 14840
  meaningful LOC).** `assistant_core/embeddings/record_manager.py` and the two
  tables it reads, `embedding_vectors` and `embedding_index_entries`, were
  declared in the assistant platform, created by a PathFinder migration and read
  by nobody inside `assistant_core`: the measurement that decided the move is
  that no module under `assistant-platform/packages/assistant-core/src/` imported the record
  manager, while six PathFinder modules did. They now live in
  `apps/api/src/pathfinder/integrations/embeddings/` - `record_manager.py`, and
  `tables.py` mapping both rows on a new declarative `EmbeddingBase`, which is
  possible where the runtime's shared `Base` was not because these two tables
  carry no foreign key. `alembic/env.py`'s `target_metadata` is the list of both
  metadatas and the test tree runs `create_all` on both; the migration itself
  writes frozen DDL and imports no model, so it needed no rewrite and stays
  PathFinder's. **The embedder is copied, not shared**: `assistant_core` keeps
  `embeddings/embedder.py` (protocol, `get_embedder`, `EMBEDDING_DIMENSIONS`,
  `EmbeddingUnavailableError`, OpenAI and fake) because `memory/{embedding,store,
  lifespan}.py` read it, and the MCP unit has its own copy of all four modules -
  the duplication `the-runtime-is-a-package.md` already accepted for
  `RuntimeSettings`, about 230 lines against a distribution edge, with no
  re-export and no alias. `RuntimeSettings.embedding_input_char_limit` stays,
  because `assistant_core/embeddings/openai_embedder.py` still reads it.
  **Settings and sessions come from the host, in the shape batches 1 and 2
  used**: `EmbeddingSettings` carries `DATABASE_URL`, `OPENAI_API_KEY` and the
  five `EMBEDDING_*` variables under unchanged names, with
  `use_embedding_settings_source` / `get_embedding_settings` and `Settings`
  subclassing it; `integrations/embeddings/db.py` is the same shape for sessions,
  so the API and the worker install `async_session_factory` and the index shares
  their pool, while a standalone MCP process builds its own engine from
  `DATABASE_URL` instead of opening a second pool beside one it does not have.
  `tests/unit/test_veupathdb_mcp_unit_boundary.py` dropped its
  `assistant_core.embeddings` / `assistant_core.platform.config` allowance and is
  the acceptance criterion; `grep -rn record_manager assistant-platform/packages/assistant-core/src`
  is empty and the package's own suite is green in its own environment (354
  unit). Two hand-offs closed with it: `NonFiniteToNone` and
  `NonFiniteToNoneRounded` lost their last consumer when batch 2 copied them into
  `veupathdb/model.py`, and are deleted from
  `assistant_core/platform/pydantic_base.py`; and the two sha256 pin-drift checks
  in `devtools/{wdk_fixtures,eda_schemas}.py` are folded into one
  `devtools/pins.py` holding `VendoredPin` and `pin_drift`, with `SchemaPin` and
  `VendoredRaml` subclassing the model and `schema_pin_drift` /
  `raml_pin_drift` supplying their own directory and glob. Recorded as [the
  embedding index belongs to the MCP
  unit](decisions/the-embedding-index-belongs-to-the-mcp-unit.md). Verified:
  `final_edges.py` reports 0 for `U1 U2`, `U1 U4`, `U3 U4` and `U3 U2`;
  ruff, ruff-format, mypy (`634` files), pyright, import-linter 7 kept / 0 broken,
  vulture, the weak-assertion and file-size gates, `openapi check` with no spec
  change, both vendor `verify` commands, and 4961 unit tests.

## 2026-09-04

* **The MCP server no longer imports anything above itself: 54 upward edges
  became 0, and its served closure fell from 162 modules / 17869 LOC to 133 /
  15027.** The module set that becomes the `veupathdb-mcp` distribution
  (`mcp/**`, `services/{catalog,wdk,gene_lookup}/**`,
  `services/tool_payloads.py`, `services/control_{tests,helpers,types}.py`,
  `integrations/embeddings/**`) reached `pathfinder.platform`,
  `pathfinder.persistence` and the application's half of `pathfinder.services`
  54 times; the count is now 0, and the only `assistant_core` edges left are the
  nine into `embeddings.{embedder,record_manager}` plus one runtime-settings
  read, which the embedding move takes next. The two paths from the served
  entrypoint to `pathfinder.persistence` are cut: `mcp/auth.py` now verifies
  the ES512 signature through the client library's own `validate_oauth_token`
  and names the caller by the OAuth subject (cached per token for five minutes
  in `mcp/identity.py`), where it used to map the token onto a `users` row and
  stringify the id; and `attach_control_downloads`, which wrote the `exports`
  table, moved up to `services/export/control_downloads.py` beside the agent
  tool and the durable job that want the links. `services/gene_sets/__init__.py`
  is empty, which drops 1009 LOC of gene-set store and `platform/store.py` out
  of the closure. The server's own foundation lives under `pathfinder/mcp/`:
  `locks.py`, `tool_errors.py` (which `ai/tools/**` now imports from there),
  `service_tokens.py`, `settings.py` (`McpSettings`, which
  `pathfinder.platform.config.Settings` subclasses, env var names unchanged),
  `identity.py`, `logging_setup.py` and `__version__ = "0.1.0a1"`. The catalog
  machinery takes its process concerns as arguments -
  `DiscoveryService(cache_dir=, budget_bytes=, policy=, spawn=)` and
  `preload_all(readiness)` - so no unit-3 module reads `platform.config`,
  `platform.tasks` or `platform.readiness`. Misplaced code moved down:
  `services/enrichment/{types,params,parser,ranking,html,service}.py` ->
  `services/wdk/enrichment/`, the by-value half of
  `services/gene_sets/enrichment.py` -> `services/wdk/enrichment/gene_ids.py`,
  `services/gene_sets/wdk_helpers.py` -> `services/wdk/gene_set_steps.py`,
  `services/search_rerank.py` -> `services/gene_lookup/rerank.py`,
  `get_estimated_size_for_site` -> `services/wdk/step_size.py`, and the control
  result and context types -> `services/control_types.py`.
  `tests/unit/test_veupathdb_mcp_unit_boundary.py` (247 cases) is the gate: it
  walks the unit and it walks the entrypoint closure. Recorded as
  [the MCP server writes no PathFinder table](decisions/the-mcp-server-writes-no-pathfinder-table.md).

* **The VEuPathDB client library no longer imports anything above itself: 84
  upward edges became 0.** The module set that becomes the `veupathdb`
  distribution (`integrations/veupathdb/**`, `integrations/eda/**`,
  `domain/{parameters,strategy,search,wdk_values}`, the `domain/eda*` modules)
  reached `assistant_core` 56 times and `pathfinder.platform` 28 times; both
  counts are now 0, with every file still where it was, so the later folder
  move is a prefix rename and nothing else. A new package
  `pathfinder/veupathdb/` holds the foundation: `model.py` (`CamelModel`),
  `json_types.py`, `logging.py` (a bound `structlog` logger and nothing else),
  `errors.py` (`VEuPathDBError`, a seven-member `VEuPathDBErrorCode`, and the
  classes the client raises), `settings.py` (`VEuPathDBSettings` plus a
  settings source that `pathfinder.platform.config.Settings` installs itself
  into, env var names unchanged), `auth_context.py`
  (`veupathdb_auth_token_ctx`, deleted from `platform/context.py`), `text.py`
  (`platform/text.py` deleted) and `observer.py`. The six WDK and site-search
  instruments are now an `Observer` protocol with a no-op default;
  `platform/metrics.py` holds the OpenTelemetry adapter and `main.py`'s
  lifespan installs it, with the instrument names and full attribute sets
  asserted through an in-memory reader. The transport gains one handler
  mapping `VEuPathDBError` to `ProblemDetail` under the same code string and
  status, so the wire and `packages/spec/openapi.json` are unchanged. Four
  catalog modules (`discovery`, `discovery_service`, `disk_cache`,
  `catalog_metadata`) and `get_discovery_service` moved down to
  `services/catalog/`, so `integrations/veupathdb/factory.py` imports no
  embeddings, sqlalchemy, readiness or task spawner. The catalog snapshot that
  `api` and `wdk-mcp` share through the `catalogs_cache` volume now carries
  `SNAPSHOT_FORMAT_VERSION`; a snapshot of another format, or of none, is
  refused with a warning naming both and the caller rebuilds cold.
  `tests/unit/test_veupathdb_unit_boundary.py` is the acceptance criterion.
  Reasoning and the rejected fifth distribution:
  `decisions/the-client-library-owns-its-foundation.md`.

* **Gene lookup reads site-search's streaming form, so a page past record 50
  exists.** Site-search declares `POST /site-search` twice on one path and the
  `Accept` header picks the form: the JSON one is capped at
  `MAX_RECORDS_IN_PAGED_RESPONSE = 50` and the ND_JSON one carries the whole
  match set. `services/gene_lookup` sat exactly on that cap, so
  `GET /sites/{id}/genes/search` reported a count it could not page to and the
  workbench's infinite scroll stopped at the first pool. `stream_records` on
  `SiteSearchClient` reads the streaming form line by line into
  `SiteSearchStreamRecord`, bounded by the caller, and `lookup_genes_by_text`
  calls it only when `offset + limit` passes 50; the paged form still serves
  the first page, the organism facets and every 50-bounded caller, because a
  streamed record carries an identifier, a score and a project and nothing
  else. The window is described from WDK after it is cut instead of the whole
  pool being described before it. Measured on plasmodb for a query matching
  352 genes: 8 paged requests, 10.54 s, 588,186 bytes against 1 streamed
  request, 0.55 s, 10,044 bytes, for the same 352 identifiers in the same
  order. The declared 100,000 record ceiling is **not** enforced by the
  deployment - the same service streamed 1,175,519 records and 32,886,583
  bytes for an unrestricted gene query - so the bound is ours
  (`SITE_SEARCH_STREAM_LIMIT`). Contract, both forms, and every measurement in
  `wdk/rest/site-search-contract.md`; the pinned response is
  `veupathdb-py/src/veupathdb/testing/fixtures/wdk/site_search_stream_genes.json`, checked against the live
  service by `tests/live/test_site_search_stream_drift.py`.

* **The recorded EDA bodies now answer to the EDA service's own spec.**
  `VEuPathDB/service-eda` publishes one merged RAML 1.0 type library,
  `schema/library.raml`, 414 types, and it is the only machine-readable
  description of the surface `integrations/eda` calls: no OpenAPI artifact
  exists anywhere in the org, and the org's own generators emit Java and
  Kotlin from this same file. It is now vendored with its one include
  (`lib-hash-id` v1.1.0 `hash-id.raml`) at
  `b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f`, sha256 per file, under
  `veupathdb-py/src/veupathdb/testing/fixtures/eda/upstream/`, and
  `python -m veupathdb.devtools.eda_schemas verify` converts it to JSON
  Schema draft-07 offline and validates all **9** recorded bodies against the
  type their endpoint returns. The 9 bound types reach **40** of the 414. No
  maintained RAML 1.0 parser exists to lean on - `ramlfications` 0.2.2 is
  RAML 0.8 only and `pyraml-parser` last shipped in 2019 - so the converter is
  ours: 10 RAML built-ins, `?` and `required: false`, `[]`, `|`, `enum`,
  inheritance, `discriminator`/`discriminatorValue` resolved to the leaf set,
  `additionalProperties: false`, and the `//` any-name property, with a strict
  declaration model that fails the parse on a nineteenth facet rather than
  dropping it. **Ten specification defects** are declared and excluded, each
  measured: `API_Variable.isCategory` absent on 13 of 13 variables;
  `API_StudyOverview.shortDisplayName` absent on 14 of 757 studies;
  `DatasetPermissionEntry.shortDisplayName` absent on 22 of 878 entries; the
  two matching `description` members absent only in the recorded copies;
  `DifferentialExpressionPoint.pointId` sent as **`pointID`** on 5511 of 5511
  rows and as `pointId` on 0; `pValue` and `adjustedPValue` absent on 1 of
  those 5511; and `pValueFloor`/`adjustedPValueFloor` sent on every statistics
  response and declared nowhere. All ten are defects in the spec, not in
  `integrations/eda/models.py`, which already matches the wire at every one -
  nothing in the models changed. Without the exclusions the same bodies raise
  3, 9, 13, 203 and 24 draft-07 errors; with them, zero. An eleventh error
  fails the gate, and so does a row the pinned library stops contradicting, so
  a fix upstream forces the table to shrink. Recorded in
  `eda/rest-surface.md`, anchored to
  `tests/unit/devtools/test_eda_fixture_schemas.py` and
  `test_eda_raml_converter.py`.

* **The two live-lane reds were measured, and neither was the fault it looked
  like.** The enrichment check asked for 200 gene ids off a transcript step and
  compared the answer to 200; a transcript step lists one row per transcript, so
  the raw slice held four repeats and `enrich_gene_ids` correctly analysed 196
  distinct genes - the same 196 WDK reported for the dataset step it built. The
  check now takes 200 distinct ids. The hidden-default sweep died on a transport
  failure in its metadata phase, which looked like a timeout that was too small:
  measured over the 359 transcript searches on plasmodb at six concurrent reads,
  `GET .../searches/{name}?expandParams=true` answered 200 for 355 of them with a
  median of 0.19 s, a 95th percentile of 1.83 s and a slowest of 6.46 s, so
  nothing came near the 30 s budget. The phase now names a search whose metadata
  never arrived instead of ending a resumable sweep, which is what the measure
  phase already did. Sweep machinery moved beside `summary.py` in
  `tests/live/hidden_defaults.py`, its two `isinstance` readers became models,
  and the new seam has hermetic tests. A third finding fell out: `word-enrichment`
  no longer completes on plasmodb or toxodb - the analysis validates `RUNNABLE`
  and its status settles on `ERROR` - so the live column check records the
  analyses a site cannot complete and holds the other four to their pinned
  columns. Both measurements and the outage are in
  transport-quirks (`veupathdb-py: docs/knowledge/wdk/rest/transport-quirks.md`); WDK-ANS-007's word row now
  rests on the source alone.

* **The pre-flight now keeps only the checks WDK cannot make, and the census
  grammar is judged where the criterion is stated.** `validate_parameters`
  already read WDK's validation bundle before it ran its own checks, so the
  local second opinion sat downstream of a verdict: measured over 104 recorded
  turns holding 798 `set_criterion` calls, the pre-flight ran **339** times
  (median 2 per turn, mean 3.3, max 12) and 31 refusals in the whole artifact
  corpus carried its payload - **28 vocabulary membership, 3 missing-required,
  and 0 from every other local check**. Retired with tests proving the
  surviving path: `find_missing_required_params`,
  `find_dependent_value_violations`, `unknown_params_error`,
  `missing_params_error`, `invalid_dependents_error` and their payload models,
  the five never-fired value validators (`validate_numeric_range`,
  `validate_string_length`, `validate_multi_count`,
  `validate_single_required`, `handle_empty`) and the eight-dataclass
  `ProcessedParam` union that existed to route values to them.
  `domain/parameters/_value_helpers.py` is gone: `canonicalize.py` decodes and
  vocabulary-matches directly, keeping the shape guards WDK answers with a 500
  or a 200. `unknown_params_error` was unreachable - the canonicalizer raises
  on the same condition first - and the missing-required and dependent-value
  checks are WDK's `byKey`, relayed. `wdk_rejection_error` now takes the
  `StepValidation` and builds its rows from
  `integrations/veupathdb/_failures.py:bundle_rows`, the one place a bundle
  becomes an agent payload, and `validate_search_params` reads the same bundle
  through `_resolve_search_details`, so the UI route and the tool path share
  one resolver, one seam and one refusal shape. **A definition WDK built
  without the caller's values casts no verdict either way** - level `NONE`, or
  a contextual read that fell back - and the push carries the values to the
  endpoint that judges them.

  Four of ten faults probed live on plasmodb.org are ones WDK reports nothing
  about: an unknown parameter name is a 200 with the parameter dropped from the
  stored step and `isValid:true` at RUNNABLE; a non-ISO date bound is a 500
  with no bundle; a wrong-typed filter value is a 500 with no bundle; and a
  `profile_pattern` in prose is a 200, stored, reported valid. That last one
  was refused by `create_step` and accepted by the pre-flight, so the model
  learned about it one tool call late. `read_census`, `census_states`,
  `sort_profile_pattern` and `validate_phyletic_codes` now live in
  `domain/parameters/phyletic.py` beside `encode_profile_pattern`, and both the
  push path and the pre-flight call them. The parameter-sweep DTOs
  (`SweepVariantSpec`, `SweepVariantResult`, `SweepResult`) moved out of
  `domain/parameters/optimization.py`, which was not parameter code, into
  `services/parameter_optimization/config.py` beside the config and input types
  their only consumers already read; the two of them that shared a name with the
  variant-comparison DTOs are now `SweepVariantSpec` and `SweepVariantResult`.
  `domain/parameters` went from 2,033 lines
  to 1,745 and the three pre-flight modules in `services/catalog` from 670 to
  475. WDK-PARAM-005 (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`) claimed in
  prose to be `UNENFORCED` while its own status field named the test that
  enforces it; the prose now states what `close_open_range` does and the anchor
  points at it. WDK-SITE-002 (`veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`), `WDK-SITE-004`
  and `WDK-SITE-005` name the moved symbols and the pre-flight call site.

* **The test suite now mirrors the code it tests, and the checkers carry less
  memory of their own past.** Under `apps/api/src/pathfinder/tests/unit` there is
  one test module per production module in the mirrored path; the tree went
  from 506 files to 381 with the collected count unchanged (every dropped test
  a proven duplicate, every merge checked by an assertion diff). Tests are no
  longer exempt from the 400-line cap: `scripts/check_max_lines.py` reads a
  ratchet baseline, eleven entries today, that only shrinks. The integration
  tier is hermetic: `tests/conftest.py` falls back to a Postgres testcontainer
  on any probe failure, no integration file stubs the module it claims to
  integrate (the EDA revision tests run through the recorded wire in
  `tests/_support/eda_wire.py`), the recorded EDA fixtures carry provenance and
  a live drift test, and `tests/integration/http/_authz_matrix_support.py`
  counts a streaming route as answered when it starts streaming instead of
  cancelling it. The web checker `scripts/check-weak-assertions.mjs` has no
  baseline any more: every vitest and e2e test states a value, and the timing
  dependent tests that failed under host load await their condition instead of
  sleeping. E2E lost its dead page-object members, has one credentials skip
  (`e2e/fixtures/wdk-account.ts`), and the thread-surgery journeys run on
  plasmodb (see the portal listing backlog card). The four inline enums the
  frontend used to hand-write (`ModelProvider`, `ReasoningEffort`,
  `Classification`, `EnrichmentAnalysisType`) are named on the backend and
  generated, and `EnrichmentResultsChunk.results` is typed. CLAUDE.md, the
  READMEs, `docs/DEVELOPMENT.md` and the package READMEs describe the tree as
  it is, with the gate list equal to CI and pre-commit. The final verification
  found and fixed two Evaluate-panel defects the restored route made reachable:
  the form posted `kFolds: 0` when cross-validation was off (every evaluation
  a 422), and a pasted gene set was evaluated as an empty-named WDK search
  instead of through `targetGeneIds`; both are pinned in
  `features/workbench/components/panels/EvaluatePanel.test.tsx`.
  A network capture of the same flow then found the workbench still mounting
  the chat surface the log declared deleted, with the experiment id as its
  conversation id (a 404 and a 422 on every evaluation), and the Gene Confidence
  panel sending `maxEnrichmentTerms: 0` against a `ge=1` contract; both are gone,
  pinned by `WorkbenchMain.test.tsx` and `ConfidencePanel.test.tsx`, and the
  `workbench -> conversation` boundary exception left `scripts/check-boundaries.mjs`.

* **Generating the WDK wire models from WDK's own JSON Schemas was measured and
  rejected; a drift gate was built instead.** `datamodel-codegen` 0.76.2 over
  the 78 schema files at `Service/doc/schema` can honestly replace 170 of the
  785 hand-written lines in `wdk_models.py` and `wdk_parameters.py` - the 17
  classes that match a schema field for field - and emits 2,646 lines to do it,
  207 classes for 110 distinct names, a 15.6x replacement for the deletable
  part. It would also touch 141 importing files, rewrite 15 gated rule anchors,
  need three unverifiable workaround stages (a `$ref` pre-bundler, a
  post-processor, a 121-name rename table), leave 17 `mypy --strict` errors no
  flag combination removes, and invert `extra="ignore"` in 110 of 110 generated
  models, where `--base-class` does not override the per-model
  `ConfigDict(extra='forbid')`. The parameter union cannot be generated at all:
  all eight `includes/params/*.json` are unsatisfiable, and 0 of the 20
  parameters across the recorded search fixtures validates against any of them,
  while all 6 of those fixtures plus a 4.3 MB live record type pass PathFinder's
  hand-written models. What was worth taking from the spike is now a gate:
  `python -m veupathdb.devtools.fixtures verify` validates recorded fixture
  bodies against the 41 vendored schema files that make up the transitive
  closure of the 14 names WDK's `@InSchema`/`@OutSchema` annotations bind on
  endpoints PathFinder calls, offline, at
  `f0a04136b658617a07c66151a49dd0787688084f`. Three fixtures were recorded to
  feed it (`record_types`, `record_type_build`,
  `answer_report_by_molecular_weight`) and the other nine endpoints of the
  twelve were measured once against a live site: nine schemas hold, and
  `wdk.answer.post-response` does not - a live 200 fails its own `@OutSchema`
  with 5 draft-04 errors. Rule `WDK-HTTP-004`, coverage table in
  `wdk/rest/endpoint-surface.md`.

## 2026-09-03

* **The second and third lean-down batches: one of everything.** The frontend
  keeps one UI kit (`src/components/ui`, the shadcn tree; the hand-rolled
  `lib/components/ui` twin and five direct Radix packages are gone), one chart
  library (echarts; the three recharts components are option builders under
  `features/workbench/analysis` with their option objects pinned by tests, and recharts
  left `package.json`), and one source for wire types: every hand-written
  mirror of a generated type in `packages/shared-ts/src/types.ts` is gone,
  the ledger rail reads the generated `InvestigationLedger` through its zod
  schema, and the OpenAPI post-pass emits anchored schemas in serialization
  mode so computed fields reach the client (pinned by
  `tests/unit/transport/test_openapi_post_passes.py`). `lib/` holds only what
  two or more features share; `scripts/check-boundaries.mjs` rules 4 and 5
  forbid `lib/` and `state/` from importing upward. The backend keeps one
  traversal module (`domain/strategy/tree.py`), no single-implementation
  Protocols, no `ai/context`, `ai/orchestration` or `services/wdk` re-export
  facade, and one import-linter contract for transport and AI together
  (seven contracts, `conventions/verification-gates.md`). `packages/shared-py`
  folded into `apps/api`. The MCP server and the agent toolsets render one set
  of payload models (`services/tool_payloads.py`), which exposed and fixed a
  defect: search-level control tests had reported default zeros because two
  models shared no field name. Three more defects fell out of the moves: the
  graph state pinned into the model's prompt showed a `ParamValue` repr, the
  scratchpad compaction row recorded an empty model id, and the thumbs-up and
  thumbs-down feedback had never recorded anything because the trace id it
  required was never emitted; the feedback route and its buttons are gone.
  The four stream parts registered schema-only and never emitted
  (`graph_plan`, `strategy_patch`, `optimization_snapshot`, `phase_change`)
  left the registry and the generated types with them.

* **The first lean-down batch: what nothing reached is gone, and the seed
  catalog is data.** The reachability inventory found every agent tool mounted,
  every table live and every worker task deferred by something, so the cut fell
  on code no entry point reached: 25 HTTP operations with no caller in
  `apps/web` (the experiment list, patch, delete, export, refine, re-evaluate,
  cross-validate, enrich, overlap and enrichment-compare routes among them; the
  route count is 94 production operations, asserted by
  `tests/unit/transport/test_wdk_gate_route_table.py`), the experiment phases no
  producer could switch on (`optimization_specs`, `threshold_knobs`,
  `operator_knobs`, `enable_step_analysis`, `sort_attribute` had no writer
  anywhere; `run_experiment` is five phases, pinned by
  `tests/unit/services/experiment/test_run_experiment_orchestration.py`, and
  `optuna` left `apps/api/pyproject.toml`), the three schema-anchor routes
  (replaced by the post-pass in `transport/http/openapi.py`, which encodes
  injected schemas the way FastAPI encodes its own, pinned by
  `tests/unit/transport/test_openapi_post_passes.py`), and the dead modules the
  import graph proved orphaned. The 17,722 lines of per-site seed definitions
  that were Python dict literals are `apps/api/src/pathfinder/data/seeds/*.json`
  behind a Pydantic loader (`services/experiment/seed/catalog.py`, pinned by
  `test_seed_loader.py`: 76 definitions across 13 sites, byte-equal to the
  modules they replaced). The frontend lost the files nothing imported, the
  second copy of the `data-*` renderer dispatch, the experiment proxies that
  duplicated the `next.config.ts` rewrite, and `data-verification-summary`,
  which no backend emitter produced; `data-strategy-revision` and
  `data-user-question-answers` joined `KnownDataPartKind` because the backend
  does emit them.

* **The EDA integration plan left the bundle.** `eda/plan/` held nine
  `type: Plan, status: accepted` documents, 21,204 lines of per-step task cards
  and checkboxes for a program that closed. `conventions/maintaining-this-bundle.md`
  admits decisions, backlog items, conventions and WDK references "and nothing
  else", and excludes session narrative, so the tree was inadmissible from the
  day the last batch was accepted; `check-knowledge` cannot see the violation
  because it enforces shape and links, not admissibility. What the plans pinned
  is where it belongs: the live-verified EDA facts are the thirteen reference
  documents in `veupathdb-py: docs/knowledge/eda/` (the filter algebra, the six-state job lifecycle,
  the bridge, the REST divergences), the architecture is
  [architecture fit](eda/pathfinder-architecture-fit.md), and every wire value
  the batch cards carried is asserted in the EDA tests under `apps/api` and
  `apps/web`. `eda/index.md` no longer offers a plan; the two documents whose
  Status line pointed into it now state the status alone.

* **The thread redesign plan left the bundle, and `thread/` with it.** Its six
  documents were 3,665 lines describing a rendering that now exists: the trace
  grouping rule is `buildTrace` in `@pathfinder/assistant-client` with its
  conformance suite, the `data-tool-summary` reduction is PROTOCOL section 6.3,
  the figure style is `Figure.tsx` and `Figure.test.tsx`, and the two-ground
  token layer is `globals.css` under `styles/tokenCompleteness.test.ts`. With
  the plan gone the directory held only its own index, so the directory and its
  line in the bundle root index are gone too.

* **The frozen acceptance layer is retired.** The four suites the two programs
  built - `apps/web/src/acceptance/`, `assistant-platform/packages/assistant-client-ts/tests/acceptance/`,
  `apps/web/e2e/acceptance/` and `apps/api/src/pathfinder/tests/acceptance/` -
  were collected by no script, hook or CI job, and every module skipped clean
  when its target was absent. They are deleted, along with the `eda_acceptance`
  marker, the `addopts` line that deselected it, the two env-gated playwright
  projects and the `test:acceptance` script. Four contracts had no assertion
  outside them and now do; see
  [a frozen acceptance suite is not a test tier](decisions/a-frozen-acceptance-suite-is-not-a-test-tier.md).

* **No endpoint reports the resolved principal.** `GET /api/v1/me/principal`
  had no caller, so it is gone; a caller learns its application from the
  service token it presents. The bearer, cookie, service-token, guest and
  forged-credential cases now run against the principal dependency on a route
  the test module owns (`tests/integration/http/test_principal_auth.py`). The
  dead helpers vulture reads at confidence 60 went with it: the three
  `from_list` classmethods on the strategy AST, two plan-tree collectors, the
  enrichment `is_enrichment_analysis`, `infer_enrichment_type` and
  `parse_enrichment_from_raw`, the ranking `best_ratio` and `ratio_sort_key`,
  and the two control-test count helpers in `tree_evaluation.py`.

## 2026-09-01

* **A pass that stops early now says so, continues itself, and can no longer
  blame the site.** A dispatch that exhausted its call budget, or that the
  repetition guard ended, was logged and dropped: the Lead read a partial spec
  with no record of the cause and reached for an external one. The stop is now
  a typed `PhaseStop` - which pass, why, the calls it spent, the criteria it
  bound against the count it was sized for - recorded on `LeadDeps` on both
  stop paths and cleared when the next dispatch starts, so a clean pass never
  inherits a stale stop. The ledger carries it off the wire and
  `render_summary` names it, which is the text the Lead reads before it
  answers. A budget stop that bound a criterion the pass did not start with is
  dispatched once more by `run_frame` itself, with a continuation work order
  that prints what is bound and asks only for the rest, sized by the same
  `criteria_floor`; a turn that started from a strategy continues as an edit,
  because an edit owes a disposition per criterion. A pass that bound nothing
  and a repetition stop are reported instead of retried. Finally
  `blamed_the_site` refuses a reply that names the site beside a transient
  state while no step failed and none came back empty, and the refusal hands
  the model the real stop to write; it fires once per turn, as the
  unverified-build refusal does. Proven by
  `tests/unit/ai/lead/test_a_stop_reaches_the_lead.py` (a scripted loop stopped
  by its budget records the reason and the numbers, a repetition stop records
  its own, a clean pass records none and clears an earlier one, the rendered
  summary names the stop, and the retry runs once, is sized by the thread,
  continues an edit as an edit, and never runs after a pass that bound
  nothing) and `tests/unit/ai/lead/test_a_stop_is_not_the_site.py` (the matcher
  and the output validator, including a reply that names a real WDK failure
  standing unchanged). Decision:
  [a budget stop is retried by the system](decisions/a-budget-stop-is-retried-by-the-system.md).

* **In-run compaction now bounds the wire context, and a planning pass is
  sized by what the thread states.** `compact_exhausted_history` keeps the
  newest exchanges until a token budget is spent - half the compaction
  threshold - instead of a fixed count of them, with a floor of two exchanges
  so a pass can always act on its latest result. A fixed count was the wrong
  unit: a few vocabulary reads carry more text than the whole middle, so the
  kept tail was the weight and the output stayed above the threshold that
  triggered the pass. The head now carries exactly one digest however many
  times the processor runs: a digest already on the head is recognized by its
  opening line, dropped, and its lines carried into the new one, so nothing an
  earlier pass summarized is forgotten and compacting a compacted history is a
  fixpoint. Sizing a phase pass reads the thread and not only its caller:
  `criteria_floor` takes the largest of the criteria on the spec the turn
  started from, the criteria on the spec the thread holds, and what the stated
  requirements name - one per criterion-shaped requirement label, one per term
  of a stated combination, whichever is larger - clamped to the count
  `MAX_PHASE_TOOL_CALLS` can honor. `run_frame` runs at
  `max(expected_criteria, criteria_floor(state))`, so a declared count may
  raise the budget and may not lower it below the evidence. Proven by
  `tests/unit/ai/agents/test_compact_history.py` (fat recent exchanges compact
  below the threshold, an oversized newest exchange still keeps the floor
  verbatim, a second pass leaves one digest that still holds the first
  middle's lines), `tests/unit/ai/lead/test_budget_scales_with_criteria.py`
  (an empty thread floors at zero, a twelve-requirement thread naming eight
  criteria floors above eight, a chatty thread cannot spend the whole turn)
  and `tests/unit/ai/lead/test_reframe_is_sized_by_the_thread.py`.

* **A stated combination is a typed requirement, and three layers check it.**
  `ConstraintKind.COMBINATION` carries one operator over two or more terms in
  the canonical form `<term> OR <term>` (or AND), parsed by
  `CombinationRequest.parse`. The terms are the user's own phrases, not
  criterion ids, because a build renumbers the criteria on the step ids it
  mints and the words survive that. `merge_constraints` keys a combination on
  its value, so a second one is a second dimension rather than an overwrite.
  `domain/strategy/combination_check.py` matches each term to the criterion
  whose text and search name share the most words with it, and reads the
  operator of the combine where those criteria meet, treating a transform as
  transparent and a single-input combine as a pass-through. A tie or a term
  that names nothing abstains: the check never guesses which criterion the
  user meant. `set_structure` runs the check on the PROPOSED tree and raises
  `ModelRetry` naming the expression, the operator found and the one required;
  `_digest_the_build_supports` runs it on the committed spec and rewrites a
  success verdict to `FailureCause.STRUCTURE_VIOLATION`, so a zero root caused
  by the wrong operator is reported as that and not as a threshold to relax.
  The grounding of a constraint now lives in
  `domain/strategy/constraint_grounding.py`, because grounding a combination
  needs the criteria and the tree and `operational_spec` already imports
  `constraints`. Consult answers land in `requirements` as typed constraints
  too, `COMBINATION` when an answer reads as an expression and `OTHER`
  otherwise. Proven by
  `tests/unit/domain/strategy/test_combination_check.py`,
  `tests/unit/domain/strategy/test_constraints.py`,
  `tests/unit/domain/strategy/test_constraint_grounding.py`,
  `tests/unit/ai/agents/test_frame_toolset.py` (the four-kinase drug-target
  shape: intersecting the two evidence lines is refused, unioning them is
  written), `tests/unit/ai/lead/test_consult_user.py`,
  `tests/unit/ai/lead/test_dispatch_deps_combination_requirements.py` and
  `tests/unit/ai/lead/test_digest_cannot_outrank_the_structure.py`.

* **The wire carries each agent's context fill, and the rail draws it.**
  `data-sub-agent-call` and `data-lead-usage` carry `contextTokens` and
  `contextWindow`: the input size of the agent's latest request, and the
  model's window from the catalog. `RunUsage.input_tokens` accumulates over a
  run, so one request's size is the delta between two readings; the sub-agent
  emitter keeps that delta in a `_ContextMeter` per dispatch and the Lead
  keeps it on its run capture. An unknown model reports a window of 0, and
  the row then shows tokens with no bar. The Progress rail's Summary tab
  renders one bar per agent that is still running, so history the runtime
  sheds mid-run is visible as the bar dropping. Protocol 1.6.0.

* **A treebox read renders the investigation's organisms first.** The 80-line
  cap in `render_vocab_tree` used to cut a portal-wide organism tree in WDK's
  alphabetical order, so a P. falciparum investigation reading `ms_assay` on
  `GenesByMassSpec` saw Anopheles and Entamoeba samples and no Plasmodium
  entry. `read_parameter_options` now takes a `VocabNarrowing` carrying the
  query and the organism hints; `_prioritized_branches` reorders every level
  of the tree so branches that name a hint come before the rest. Nothing is
  filtered and no leaf is lost: the reorder happens before the cap. The hints
  are the `ORGANISM` requirements the thread accumulated
  (`organism_hints_from`), threaded through `AgentToolState.organism_hints`.
  The MCP entry point passes no hints and reads the WDK order.

* **The per-criterion tool budget is ten calls, not seven.** Two FRAME
  dispatches on an 8-criterion portal prompt died on a scaled ceiling of 78
  while asking for 80 and 81, and the second ended the turn asking the user
  for a mass-spec experiment accession that one `query=` read would have
  returned. On a vocabulary-heavy site one criterion costs an overview read
  plus several vocabulary reads plus name-correction retries, so
  `CALLS_PER_CRITERION` is now 10. The floor, the cap and the token ceiling
  are unchanged.

* **An EDA-exported turn leaves exactly one case.** The live re-proof of the
  program's finding wrote two: the export's case and an "outcome" case that
  credited the turn's FRAMED-but-never-built spec with the export's 1,543.
  The collector now returns the export's case alone when the count came from
  an export; a spec the turn framed but never built may not claim the result.

* **An EDA export is a build, and a built turn cannot end silently
  unverified.** `create_eda_step` now records the turn's `BuildOutcome`
  through the same `PipelineState.record_build` seam the build and edit
  dispatches use, so an exported step sets `turn_markers.built`, feeds
  staleness, and shows in `ledger.build` with the count the commit's sync
  read. A commit that did not reach VEuPathDB records nothing: that step is a
  draft on the canvas with no size, and the ledger keeps the last build the
  site took. The composition of that outcome is one function,
  `services/strategies/graph_outcome.py::outcome_for_graph`, which the edit
  dispatch now calls too.

  A verified EDA arc used to write no case at all: `collect_case_candidates`
  required `operational_spec.criteria`, and the EDA arc never dispatches
  `frame_problem`. An EDA-built turn now leaves a case composed from what that
  arc has - the study display name, the analysis name and the filter summaries
  from the analysis card the thread last rendered, the volcano cut the export
  applied, `original_request` as the goal, and the exported step's own count
  (not the strategy root's, which can hold a different number). The card's
  state is a typed `EdaAnalysisFacts` on the domain state instead of a JSON
  digest string, so "has the card changed" is Pydantic model equality, and the
  export the case reads is an `EdaExport` on `TurnMarkers`, which rotates with
  the user message and so cannot be re-remembered by a later turn.

  The precondition gate offers `verify_strategy` at the right step but cannot
  compel the call, and one live heat-shock turn closed with "I'm stopping here
  rather than report a gene count" after a successful export. An output
  validator on the Lead now refuses the first answer of a turn that built
  something and neither dispatched nor passed verification. It fires once,
  tracked on `TurnMarkers`, so a second answer that states why a check is
  impossible still reaches the user: the nudge compels the attempt, not the
  outcome. The deterministic mock's edit arc verifies what it edited, which is
  what the instructions already asked of it; the eval corpus stays 8/8 with no
  arc tripping the validator.

* **The step tree has one owner again, and the sentinel answers nothing.**
  `fold` in `domain/strategy/tree.py` hands each node its inputs
  already folded, in slot order, and the six raw recursions over
  `primary_input` outside `domain/strategy/` are written on it or on
  `walk`: the eval comparison tree and structure signature, the
  step-analysis prune and branch extraction, the WDK step-tree projection, the
  parameter canonicalization pass and the experiment materializer. The wire
  tree got the same treatment through `integrations/veupathdb/step_tree.py`;
  `_trees_equal` went with it, because two `WDKStepTree` models already compare
  structurally. `input_resolution.py`, which the card named as the largest
  recursion site, holds none: its 40 matches are local names over the flat
  model, and the one type that mentioned the AST was a dataclass nobody
  constructed.

  `__combine__` is now produced only inside `domain/strategy/` and read by
  nobody to decide what a step is. `own_search_name` is the single translation
  from the persisted name to "this step names no question", `runs_a_wdk_search`
  is the predicate the push and validation paths were spelling out by hand, and
  the duplicate literal in the context renderer is gone. The name never crossed
  the WDK wire in the first place; the reasoning is in
  [the sentinel decision](decisions/the-combine-sentinel-is-a-boundary-default.md).

  One rule picks the root. `StrategyGraph.primary_root_id` (largest subtree,
  ties to the step added first) replaced both remaining heuristics. The one in
  `build_context_strategy_ast` had been falling back to `last_step_id` whenever
  the canvas held more than one root, so a stray leaf added after a two-step
  strategy made that leaf the root of the AST the model reads and pushed the
  real strategy into `detached_roots`; the second, in `push_steps_with_plan`,
  picked an arbitrary member of a `set` to answer "is there a root at all".

* **A verified investigation now leaves a case behind.** The store's kind union
  grew a fifth member, `case`, and `finalize_turn`'s digest-success branch writes
  one through the same tombstone-filtered auto-write the other kinds use
  (`ai/lead/case_memory.py` -> `collect_memory_candidates`). An outcome case
  carries the goal the thread is answering, the structure line, the criteria with
  their bound params and the root count the build reached. A recovery case carries
  the search that emptied a step of this thread and the params that filled it:
  `StrategyDomainState.zero_result_history` records each emptied search at
  `record_build`, and a later build that fills one writes the pair. Both key on the
  content hash, so the same case written twice is one row and a user's delete
  tombstones exactly that content. FRAME's procedure now opens by reading what
  already worked - `search_memory(query, kind="case")` for this user's verified
  runs and `search_example_plans(query)` for public VEuPathDB strategies, which was
  registered on FRAME's toolset but named nowhere in its instructions. The route,
  the response schema and the Memory tab list and delete cases like any kind; the
  dead `state/useMemoriesStore` that duplicated the group list with no consumer went
  with the change.

* **Sequencing rules the Lead used to read as prose are preconditions the
  prepare hook enforces.** `ai/lead/intent_gate.py` grew from one gate into
  the precondition layer: `apply_tool_preconditions` hides everything but
  `UNCLASSIFIED_TOOLS` (classify, the two state reads, the two literature
  reads, `remember`) until THIS turn classifies its own message, then hides
  `BUILDING_TOOLS` unless the classification asks for a build, then hides each
  phase tool whose precondition is unmet - `frame_problem` after a frame this
  turn, for an edit over criteria that already have steps, and after a build
  of this turn left a step empty; `build_strategy` once the graph holds a
  step; `verify_strategy` until a build outcome or a step exists and again
  once a verification of this turn succeeded; `create_eda_step` until
  `preview_eda_subset` counted the open analysis this turn. The turn's record
  is `TurnMarkers` on `StrategyDomainState`, keyed by `user_message_id`, so a
  resumed turn (approval answer, durable result) keeps what it did and a new
  message starts empty; `PipelineState.turn_markers` is the one accessor and
  `PipelineState.record_build` is the one writer of `last_build_outcome`. Each
  gated tool's description now states its own precondition, and the
  instruction rows the gate enforces are deleted (classify-first, frame ONCE,
  the build refusal, no re-frame on zeros, verify-when-built, no re-run of a
  succeeded phase); the intent rows stay. The deterministic provider meets a
  hidden `build_strategy` as an absence rather than a refusal, so
  `mock_arcs._build_refused` reads either. `ai/graph/lead_node.py` (408) split
  at the seam it had: `ai/graph/_lead_delta.py` owns the state update the turn
  writes back. Verified: 19 new unit tests, the four existing gate pins
  updated to the new contract, 4094 unit tests green, ruff, ruff-format, mypy
  strict and pyright clean on the 18 files touched, `check_max_lines`,
  import-linter 8 kept and vulture clean, and the 8-case eval corpus on the
  deterministic provider.

* **The Lead opens each turn on what moved since its last one.** A fifth
  pinned instruction, `pinned_turn_briefing`, renders a "Since your last turn"
  section composed from four reads the code already had and nothing read:
  the newest two `strategy_revisions` rows diffed at parameter level
  (`domain/strategy/ast_diff.py`, by step id, so a search swap, a parameter
  edit and a step added or removed each name themselves), the durable tasks
  that reported after the thread's newest assistant message, the
  `conversation_analyses.revision` delta against the revision on the newest
  `data-eda.analysis-state` chunk in the thread, and the requirements whose
  grounding differs between the two revisions (the same `ground_constraints`
  the ledger uses, run against each side's searches and parameter values).
  The reads are one service, `services/conversations/thread_activity.py`;
  the composer, `ai/lead/turn_briefing.py`, is pure over its typed result and
  renders like `StaleBuild`: at most eight lines, then `and N more changes`,
  and the empty string when nothing moved, so a quiet turn pays nothing. The
  hook that populates it is `pre_turn.attach_turn_briefing`, composed with
  the WDK refresh into `pathfinder_pre_turn`, which the graph is now built
  with. `pinned_user_memories` is registered on the Lead as well as the
  sub-agents, so the memory sentence in CLAUDE.md is true: the render binds
  to a `CarriesMemories` protocol rather than to either deps type. Two files
  split along a seam each already had: `ai/graph/_lead_turn.py` (450) is now
  the parked-call half plus `ai/graph/_lead_answers.py`, which owns reading
  the user's answer, and `ai/lead/lead_agent.py` is the agent plus
  `ai/lead/lead_pins.py`, the five renders it pins. Verified: 18 new unit
  tests (the differ per change kind, the composer per input kind, the quiet
  render, the elision, the worst-case character bound, the pin, and the Lead
  rendering the memories its turn retrieved), 3 new integration tests through
  the real hook on a seeded thread, the instruction-order pin,
  `check_max_lines` clean on every file touched, ruff, ruff-format, mypy
  strict and pyright clean on the 18 files, and import-linter 8 kept 0
  broken.

* **Two modules over the 400-line gate split along the seam each already
  had.** `ai/models/mock.py` (440 meaningful lines) is now the role table
  and the sub-agent scripts (106) plus `ai/models/mock_arcs.py` (362), the
  Lead's turn arcs: the prose, the routing markers, the build / edit /
  remember / recall / consult sequences and `lead_script`. The core reads
  seven public names off the arcs module (`spec_for`,
  `verification_succeeds`, `SUCCESS_PROSE`, `FEEDBACK_PROSE`,
  `LOOP_MARKERS`, `LOOP_CALL_ARGS`, `lead_script`), so no module reaches
  into another's privates. `jobs/runner.py` (401) is now the job wrapper
  (195) plus `jobs/completion_turn.py` (226), which owns the turn a
  finished durable task opens: `CompletionOutcome`, `safe_completion_turn`
  and everything under it. No shim, no alias, no re-export: the four
  callers and the two monkeypatch targets name the new modules directly,
  and `PATHFINDER_SCRIPT`, `get_mock_model` and `run_durable_task` keep
  their import paths. Verified: `check_max_lines` reports all five files
  OK, ruff, ruff-format, mypy strict and pyright clean on the touched
  files, import-linter 8 kept 0 broken, 240 unit tests and 83 integration
  tests over every consumer of either module, and the frozen durable
  acceptance file passes untouched.

* **The agent can see its own budget, and four tools disclose instead of
  dumping.** `pinned_run_budget` renders `tools N/limit - tokens X/limit`
  from the run's own `RunContext.usage_limits`, pinned on the Lead and on
  every sub-agent, so the ceiling that ends a run mid-task is visible while
  there is still budget to steer with; a context no run backs renders
  nothing. The four largest tool results on the wire were cut to a ranked
  index with a handle: `web_search` 11,201 -> 2,961 bytes and
  `literature_search` 18,259 -> 5,040 (the leading three results carry their
  text, the rest carry the identity that fetches it again),
  `search_eda_studies` 4,323 -> 2,648 (`describe_eda_study` reads the picked
  study in full), and the `set_eda_filters` sheet 9,595 -> 6,291 (a field the
  variable does not declare is not serialized, and a vocabulary the study
  already cut travels as a shorter sample of the same form). Every filterable
  variable still reaches the sheet with its own example, because a variable
  missing from it is a filter the model cannot write. Each ceiling is pinned
  in a test against the serialized tool return.

* **The Lead is told what the machine guarantees.** A generated preamble,
  built from an explicit reversibility class per tool plus the registry's own
  markers (`requires_approval`, `BUILDING_TOOLS`, the durable registration,
  the dispatch phase role), is pinned as `pinned_machine_guarantees`: every
  strategy write appends a revision and a revert restores it, a destructive
  tool is held for the researcher's approval, a success verdict is held down
  to the build, and an undeclared spec change is refused. A unit gate holds
  the map complete against the 26 registered tools, so a new tool with no
  class fails before it reaches the preamble. `clear_strategy`'s docstring
  no longer claims a cleared strategy loses its provenance: clearing appends
  a revision like any other write.

* **The agent-ergonomics program opened.** Seven claims about how legible
  the system is to the agent driving it were audited against the code; none
  refuted, several corrected (the intent gate carries a stale classification
  across turns; `search_example_plans` is semantic but unadvertised; the
  graph rewrite left M-sized residue, not the old review's L). Seven cards
  carry the measured evidence and the order of work.

* **A tool's prose names the arguments the tool declares.** Two tool names
  the prose taught no longer existed (`run_control_tests`, and `build_step` /
  `combine_steps`), and eleven surfaces taught a camelCase argument for a
  snake_case parameter - the shape that earns an `extra_forbidden` retry.
  All are corrected, and `list_notes` / `search_notes` now return
  `NoteListResult` / `NoteSearchResult` instead of describing an envelope no
  model declared. The gate is one parametrized test over the 83 registered
  tools: no docstring, parameter description or `ModelRetry` string carries
  the camelCase of a declared parameter, and every code-quoted tool-shaped
  identifier resolves to a registered tool. It was red on 14 tools before the
  fixes, and it is red again on any one of them reintroduced. Prose about a
  RETURNED field keeps camelCase, because that is what the wire carries.

## 2026-08-31

* **The lead closed the fork/revert program.** The journey's turn 4 now
  asserts the build refusal it really gets (it had passed over a verification
  that never ran), a `build-refusal` spec pins the refusal end to end with a
  byte-equal AST, and the full affected e2e set - thread surgery, auto-build,
  execution phase, strategy overhaul, fork, branch switch, complex edit, the
  drug-targets journey - ran 39 of 39 green with no retries on the production
  e2e stack carrying the revert-materializes and binding-history contracts.
  The backlog is empty.

* **A revert materializes what it restores, and the EDA binding follows the
  thread's own log.** The last two invariants the case matrix filed rather
  than fixed are closed.

  A revert restored a snapshot by writing it back verbatim, so a revert inside
  a branch left a plan: `copy_prefix` writes a branch's snapshots with no WDK
  id, and the twig that had held a strategy id and four step ids of its own
  came out of the revert with `wdk_strategy_id = None` and no step ids at all.
  The revert path now adopts the snapshot through the same
  `materialize_strategy_snapshot` a branch uses, so the tree is pushed again
  and the thread owns the ids WDK answers with: the deleted turns may have
  edited the steps the snapshot names, so a fresh push is the only honest
  answer on an unbranched thread too. That makes a revert a WDK write, and
  `POST /conversations/{id}/revert-to-message` now carries the same
  `require_registered_wdk_identity` the branch route declares. A stopped turn
  still restores its pre-turn snapshot as recorded, because it is undoing
  writes made against those same steps.

  Neither branch nor revert read `conversation_analyses`, so a branch of a
  thread with a study open showed the study's turns and no study, and a revert
  past the turn that opened a study kept the study. The binding has no history
  of its own and cannot grow one from a row that is replaced in place, but the
  thread's log already records every binding state: a
  `data-eda.analysis-state` part carries the dataset, the analysis, the display
  name and the whole filter array, and the log is cut by a revert and copied by
  a branch. `services/eda/thread_surgery.py` reads the newest surviving part
  and puts the binding where it says: a branch creates an analysis of its own
  from the recorded descriptor, and a revert unbinds, refilters or rebinds in
  the four cases the invariants doc tabulates. Measured while deciding the
  rebind rule: nothing in the application calls the analyses client's
  `DELETE`, so a rebind normally finds the recorded document still on the
  service and only a `404` makes it create one. The EDA tab's own route emits
  no part, so a revert reads before the cut whether the log ever recorded a
  binding and unbinds only when it did, the same shape the strategy uses for a
  thread that predates the revision store. A refusal from the study service is
  logged and swallowed on both paths, because a document nobody can reach must
  not cost the user a branch or a revert.

* **The mock Lead now reads `build_strategy`'s refusal.** The deterministic
  script's build arc was a fixed `classify -> frame -> build -> verify ->
  final_result` list, so a second build on a thread that already had a strategy
  marched past the refusal and answered "Verified end-to-end." over an
  unchanged strategy: the one lane where a spec can watch a refusal reach the
  user could not tell a refused build from a built one. The arc now branches on
  the refusal it was given: `retry_prompt_parts` in the scripted-model
  machinery hands the script the `RetryPromptPart` a tool raised, the way
  `tool_return_parts` hands it the returns. A refused build ends the turn
  after `build_strategy` with prose that names `edit_strategy` and says nothing
  was built. A unit pin asserts the mock's marker is a substring of the real
  `build_would_replace_the_strategy` message, so the two cannot drift.

* **check:generated can fail now.** The generated tree is untracked (the
  repository index holds only the three hand-written shared-ts sources), so
  the script's exit-code diff of `src/generated` compared nothing against
  nothing and the CI job passed unconditionally. The honest invariant for
  untracked output is that the committed spec generates types that compile:
  the script is now `kubb && tsc --noEmit`. Drift between the app and the
  committed spec stays gated by the api lint job's openapi check, and every
  CI web job already regenerates the types from source (`setup-web`).

* **Branch and revert have a written case matrix, and holding it to the matrix
  found four defects.** `conventions/thread-surgery-invariants.md` states nine
  branch invariants and seven revert invariants as one testable sentence each,
  every sentence naming the test that goes red when it stops holding. Writing
  the tests first turned four sentences red.

  A copied log row was stamped with the moment of the branch while its message
  kept its source time, so the first revert inside a branch deleted every chunk
  of the turns it kept: the branch held its messages and rendered them empty.
  Copied notes had the same stamp and were also copied whole, so a branch held
  notes about work it never did. Both copies now keep their source's time, and
  the notes are cut at the anchor like the log.

  A branch of a branch opened on a plan with no WDK strategy, because the push
  was decided by the snapshot row's own WDK id and a branch's copied history
  carries none. The decision now reads the tree: every snapshot that holds one
  is pushed, and a WDK refusal still leaves the branch holding the plan. The
  conditional went with it.

  A branch inherited its source's `gene_set_id` while owning a new WDK
  strategy, so the branch's first build called `resync_strategy` on the
  parent's saved gene set and replaced its membership. The branch now starts
  unlinked and imports a set of its own; `experiment_id`, which is read and
  never written, still carries.

  Two gaps are filed rather than patched, both because the fix moves a contract:
  a revert inside a branch restores a plan (pushing would need the revert
  route's identity contract, which the fork route has and it does not), and
  thread surgery does not touch the EDA binding (the binding has no history to
  read, and `bind` leaves `created_at` at the first bind).

  The model-history cases are measured rather than argued: a scripted model
  records the messages each run is handed, and a turn on the branched or
  reverted thread must show the pre-anchor tool call and not the post-anchor
  one. Both go red when the checkpoint cutoff is removed.

* **Branching and reverting are driven in the browser, eight journeys wide.**
  `e2e/feature/thread-surgery/` runs real turns through the deterministic mock
  and asserts the surfaces a researcher reads: a branch taken at the first turn
  holds exactly the pre-anchor turns; a branch of a branch carries message ids
  no ancestor shares and reverts on its own; a turn on a branch answers from the
  Ledger it inherited and adds no sub-agent run; a branch taken at an old
  message carries that message's organism and a WDK strategy of its own; a
  revert truncates in place and puts the organism back; the reverted thread
  carries on and the deleted turns stay gone after a reload; a second revert to
  an already-deleted message is answered 204 and the dialog shows no error; and a
  branch of a thread with a study open opens an analysis of its own while the
  parent keeps its subset.

  Three harness additions carry them: `ChatPage.branchFromAssistantReply` reads
  the fork response for the id it navigates to (the route already named a
  conversation, so waiting for the pattern returned the id it was leaving),
  `openEditDialog`/`confirmRevert` drive the branch-or-revert dialog on a
  `user-edit-composer` testid, and `sendTurn`/`awaitTurn` give every turn one
  budget that covers its wait for a free worker slot. The script gained one arc:
  a recall request reads a Ledger section and answers with it, dispatching no
  sub-agent, which is what makes "the model sees the branch's history" a
  measurable claim - the Lead's run is handed no prior-turn messages at all, so
  the Ledger is the only thing a branch can inherit.

* **The lead closed the multi-durable follow-ups.** CLAUDE.md's durable
  paragraph now states the durable_calls list and the last-arrival gate; the
  frozen durable acceptance reads `task_ids` and the scalar compat property
  is gone; the serialize-spec allowlist names the state card's change digest
  (a comparison key, not an analysis document).

* **A model step that calls two durable tools is answered once, for both
  calls.** The park recorded one durable call of the step, so a run that owed
  results for two tasks was resumed with one and pydantic-ai refused the
  turn: `Tool call results need to be provided for all deferred tool calls`.
  `PendingDurableCall` now carries a `durable_calls` list (call id, tool, args,
  task, registered tool name), `_park_run` and `pending_durable_call` record
  every deferred call of the step, and `durable_tool_results` answers each one
  with its own task's result. The worker stores each result on its row and
  opens the completion turn only when the last task of the parked step has
  reported; earlier arrivals write their `data-task-completed` and stop, and
  the turn settles every row it answered. `2026_08_31_0001` flushes the
  checkpoints, PROTOCOL 1.5.3 states the several-task gap, and the thread's
  "View result" link now names only content written after the outcome.

* **The model captions its own plots, and the caption sits under the
  figure.** `EdaSubsetPreviewPart` and `EdaVizPart` gained `caption`, written
  by `preview_eda_subset` and `run_eda_compute` (the compute's rides the
  durable job's args to `_announce_volcano`) and asked for by the Lead's EDA
  loop. A part that carries one renders `Figure N. <caption> (<study> -
  <numbers>).`; a part without one keeps `Figure N. <study> - <numbers>.`, so
  the recorded acceptance turn's captions are unchanged. `Figure` gained
  `footer`, and both plots moved their readouts and disclosures into it, so
  the order is title, plot, caption, readouts, disclosures. The volcano draws
  expanded, with the collapse control kept.

* **The Lead searches for itself.** `web_search` and `literature_search`
  were registered only in the FRAME and VERIFY toolsets, so the assistant
  could ground a claim only by dispatching a sub-agent. Both are now Lead
  tools (the same thin `agent_deps_for` wrapping `clear_strategy` uses),
  never hidden by the intent gate, pinned in `test_lead_research_tools.py`
  and the seam's tool list.

* **The rail's active section is a no-op.** Clicking the Chat icon while a
  conversation was open navigated to the bare draft route and dropped the
  thread; a section link whose section is already active now prevents the
  navigation, for all three rail items, pinned in `AppNavRail.test.tsx`.

* **The gene-id disclosure copies its list.** A copy icon beside the
  "Gene ids (N)" summary writes every selected id to the clipboard as a
  comma-separated list - all of them, not the twelve the readout prints -
  without toggling the disclosure, and flips to a check while it confirms.

* **The lead closed the paper-figures pass.** The frozen figures acceptance
  now pins the numbered captions verbatim, and the subset preview's body lost
  its entity list - the same self-repetition the state card lost, satisfied
  by the caption alone (both previously-cited pins read the caption's text).

* **The data plots caption themselves like a paper, and their long lists sit
  behind a disclosure.** The subset histogram and the volcano now carry a
  centered, italic caption prefixed `Figure N.`, numbered across both plot
  kinds in thread order by a client-side reader (`figureNumbers.ts`, beside
  `analysisStateParts.ts`); `Figure` gained `numbered` and `figureNumber`, and
  a plot the thread cannot number keeps the plain left caption. The recorded
  acceptance turn reads `Figure 1. Heat shock response in sensitive mutants
  (LRR5, DHC) - 6 of 12 Sample, 6 values.` and `Figure 2. ... - 1,543 of 5,511
  genes retained.` The 28 per-bin lines and the volcano's gene ids moved into
  native `<details>` (`Bin counts`, `Gene ids (N)`), closed on first paint; the
  coverage line joins them unless the distribution reports missing cases, and
  the multivalued warning and the selection readout stay visible. The study
  card stopped restating its own caption: its body is the analysis name, the
  filter chips and the computation count, and the entity counts appear once.

* **One study card per analysis, and the plots name their study.** The
  thread now keeps only the NEWEST analysis-state card for an analysis; an
  older statement yields to it on replay and live (reader rule in
  `analysisStateParts.ts`). The "Open study" button rides the title row
  (`Figure` gained an `action` slot) instead of its own line. The subset
  histogram and the volcano caption themselves with the study's display
  name, read off the thread's own state parts, so a plot keeps its context
  when the card above it has moved on.

* **The subset histogram has a plot area again.** The chat card drew its
  distribution at 72px while the chart's grid reserves 64px for axes, so the
  bars lived in 8 pixels. The height is 220, matching the collapsed volcano,
  and a pin holds it at 160 or more.

* **The model pill is gone; the turn's numbers ride the trace.** The badge at
  the top of an assistant message read `OpenAI - gpt-5.6-luna - 41.8K, $0.01`,
  which was the Lead's own spend and never the turn's, so the one number a
  reader saw was the wrong one. `ModelBadge` is deleted. The trace's summary
  row now carries a right-aligned `trace-usage` line, still behind the
  `showTokenUsage` flag: the bare model name from `data-lead-usage`, then
  `formatUsage` over the Lead's tokens and cost plus every
  `data-sub-agent-call` the message carries - the sum the wire reports as the
  turn total. The recorded acceptance turn reads `gpt-5.6-luna - 54.1K, $0.02`
  where the pill read `41.8K, $0.01`. `data-turn-usage` could not be the
  source: the chunk is transient, so neither the AI SDK nor `reduceSnapshot`
  ever puts it on a message part. The consult recap is headed "Your answers"
  and lays each pair out as `Q:` then `A:`, one block gap apart.

* **The thread has one vertical rhythm and no rules.** Spacing between a
  message's blocks, between messages, and between fan-out lanes is the one
  `THREAD_BLOCK_GAP` token on the flex containers; the cards' outer margins
  and the figure hairline are gone, with a source-reading guard
  (`threadRhythm.test.ts`) that fails on any `my-*` or `border-t`/`border-b`
  returning to thread content. The frozen figures acceptance now pins a
  classless figure. The vendored `MessageToolbar`/`MessageAttachment(s)`
  exports nothing rendered are deleted.

* **One paragraph rhythm in the thread, and no dividers.** Blocks inside a
  message and the messages themselves were spaced by eight different values -
  `gap-8` between messages, `gap-2` between a message's blocks, and `my-2`,
  `my-3`, `my-4` and `my-6` on the trace, the task rows, the consult cards,
  the notices and every figure - so a figure sat 24 px from its neighbour and
  a task row 8 px from its. One owner now holds the vertical rhythm:
  `THREAD_BLOCK_GAP` in `lib/components/thread/rhythm.ts`, applied by
  `MessageContent` between a message's blocks and by `ConversationContent`
  between messages. Every block in the thread sets no outer vertical margin,
  and `Figure` lost the `border-t border-border/60` rule that separated one
  typed result from the next. `threadRhythm.test.ts` reads the thread's own
  sources and fails on any `my-*` or any `border-t`/`border-b` under
  `features/conversation/content/` and `lib/components/thread/`, so neither
  can come back. Structural chrome outside the message flow - the composer's
  top border, the rail and the trace's indent rail - is unchanged.

* **The study card repeats only when it changed, and the strategy update is
  a titled card.** Every `open_eda_analysis` and `set_eda_filters` call put
  the full analysis-state card on the thread, and the state's `revision`
  bumps on every mutation, so a user saw the same "No filters yet, 12 of 12
  Sample" block three times in one arc. The tools now emit the card only when
  it would read differently (`analysis_state_chunks_if_changed`, a digest on
  the pipeline state that leaves out `revision` and the raw `filters`), and
  the chunk carries the analysis id so repeats inside one message reconcile.
  A compute's completion still announces its own state (it changed). The
  `data-graph-snapshot` figure rendered a bare "1 step, 1,543 genes" line
  with no title; it now reads "Strategy updated" above the counts.

* **Three findings from the user's first session on the finished build.**
  Opening the site logged `getPrivacySettings: 401`: the eval-data notice
  fired its privacy read in the same render that starts the token refresh,
  so the read raced the cookie mint; the query now waits for the refresh to
  settle and for a signed-in status, and an unauthenticated visitor is never
  asked. The turn trace opened and closed by itself as work started and
  settled: its expanded state now belongs to the reader - open when it mounts
  mid-run, closed when it mounts settled, and after that only the toggle
  moves it. The consult card ("Questions you answered") rendered at the end
  of the message rather than in the flow: `tool-consult_user` now renders its
  card where the part sits, through the same registry every other part uses,
  and nothing else is appended after a message's parts except the turn-status
  notices.

* **A tool's prose names its parameters as the schema spells them.** The
  final live arc carried one `tool-input-error`: `create_eda_step` refused
  `effectSizeThreshold`, `significanceThreshold` and `effectDirection` as
  extra fields - names the tool's own docstring and retry messages had
  taught, in camelCase, while the schema declares snake_case. The prose now
  uses the declared names, and a pin asserts the module contains no camel
  form of them and that the docstring names all three declared parameters.
  The lead ruled the single self-corrected retry within tolerance once this
  guard landed: the error never reached the user, and the arc ended verified
  at 1,543 with the prose quoting the digest.

* **Insert-saved dropped an edit committed while it read WDK, and spliced the
  saved strategy onto itself when the target step was the root.**
  `POST /conversations/{id}/insert-saved` read the stored AST, read and cloned
  a saved WDK strategy, and only then wrote the whole tree back.
  `test_an_insert_saved_and_a_param_edit_both_land` parks the insert inside the
  saved-strategy read while a parameter edit commits: the persisted
  `text_expression` came back `kinase`, not the committed `phosphatase`.
  `insert_saved` now takes `strategy_write_lock` before its read, and
  `_record_consumer` joins that transaction through the shared
  `write_lock.py::strategy_write_scope` instead of opening a second session
  against the row the caller's transaction already holds, which is what
  deadlocked. The same test found a second fault: `_build_new_root` added the
  new combine to the graph before it looked up the target step's parent, so the
  combine answered as its own parent, `primary_input_id` pointed at itself, and
  a root-target insert persisted the pre-insert tree with the consumer already
  recorded - `['GenesByText', 'GenesByGoTerm', '__combine__']` and
  `imported=[7777]` on a solo run. The parent is now read before the combine
  joins the graph; `tests/unit/services/strategies/test_insert_saved_splice.py`
  covers a root target and a target below the root.

* **A cancel test still encoded the pre-thread heartbeat window.**
  `test_stop_on_a_starved_but_live_worker_only_asks` staged a heartbeat aged
  153 s and asserted the job stayed `doing`; with
  `worker_dead_heartbeat_seconds` at 60 the job came back `failed`. The staged
  ages now read `worker_dead_heartbeat_seconds` and
  `worker_heartbeat_interval_seconds`, so the starved case sits one beat inside
  the window and the dead case ten windows past it, and the test asserts the
  starved age is inside the window before it stages it. The stale "five to six
  minutes" in `jobs/maintenance.py::release_stalled_jobs` is now the one to two
  minutes [the decision](decisions/a-dead-worker-fails-its-turn-by-heartbeat.md)
  already states.

* **Two overlapping edits on one thread each wrote a whole tree built from the
  same base, so one of them was dropped.** `POST /operations` read
  `conversation_strategies.strategy_ast`, edited the tree in memory, pushed to
  WDK, and only then took the per-thread advisory lock for the write, so a
  second operation that read before the first committed wrote its own tree over
  it. Measured both ways in
  `tests/integration/services/conversations/test_concurrent_strategy_edits.py`,
  which parks one writer inside its WDK push while the other commits: a
  parameter edit to `phosphatase` put a committed `INTERSECT` back to `UNION`,
  and a combine-operator edit put a committed `phosphatase` back to `kinase`.
  `apply_operation` now takes the lock before the read and holds it through the
  write, and `persist_strategy_ast_to_conversation` joins that transaction
  instead of opening one of its own. The rejected alternatives, and the agent
  turn this does not cover, are
  [a decision](decisions/a-graph-operation-holds-the-thread-lock-across-its-read.md).

* **A resumed tail reads one turn at a time, so a suspended turn's card is
  drawn once.** `ai@6.0.154` builds one assistant message per stream and
  seeds it with the message the client already holds
  (`AbstractChat.makeRequest` -> `createStreamingUIMessageState`), and its
  `start` case only renames that message. A tail that carried a durable task's
  gap and then the continuation turn therefore ended with the continuation
  holding the suspending turn's parts: measured on the e2e stack's production
  build as one `data-background-task-started` frame on the wire (1 chat POST,
  2 tail GETs, 1 snapshot) and two `Optimize parameters / Completed` rows,
  with `durable-progress-live.spec.ts:137` red on a strict-mode violation.
  `DurableChatTransport` now ends a resumed stream at a `start` that opens
  another message, keeps the frame iterator, and serves the rest to the next
  resume; `resumeDurableThread` opens that message first, so no second request
  is made and each turn is read into its own message. PROTOCOL 1.5.2 states
  the reader rule in section 9. The rejected alternatives are
  a decision (`assistant-platform: docs/knowledge/decisions/a-resumed-stream-reads-one-turn.md`).

* **The e2e stack serves the production build, and the suite finishes in one
  process.** `docker-compose.e2e.yml` pins `web.build.target: runner`, which
  overrides the dev overlay's `dev` target and makes the local recipe build the
  image CI already built. The dev server it replaces compiled a route on every
  first request and kept the result: 7.44 GiB of anonymous memory, then
  `OOMKilled=true` part way through a run that ended `54 failed / 1 skipped /
  66 passed`, 47 of them on `ERR_CONNECTION_REFUSED`. Rebuilt on the dev target
  to compare the two, it did not even survive the global setup's twelve route
  requests - dead in 2 m 48 s, with single compiles of 14.8 s to 23.4 s in its
  log. The production container holds 96 MiB at boot and 182 MiB mid-suite, and
  one `playwright test --retries=0` process now runs all 158 tests. The
  reasoning and the rejected alternative - `mem_limit` plus
  `--max-old-space-size` on the dev server - are
  [a decision](decisions/the-e2e-stack-serves-the-production-build.md).

* **Neither dev overlay reaches the suite any more, and the devtools bubble is
  off the nav rail.** A production build mounts no `<nextjs-portal>`, and
  `@tanstack/react-query-devtools` 5.95.2 resolves its own entry to
  `function () { return null; }` unless `NODE_ENV === "development"`, so the
  seven specs that timed out on a click an overlay swallowed
  (`settings.spec.ts:8,13,22`, `auth.spec.ts:64`, `memory-settings.spec.ts:5`,
  `full-researcher-lifecycle.spec.ts:19`, `workbench-panels.spec.ts:235`) are
  green; the lifecycle journey that burned its whole 720 s budget on the retry
  loop finishes in 47.3 s. For the dev stack, where the toggle does render, its
  `buttonPosition` moves off the left edge the nav rail owns, pinned by a
  vitest. `no-dev-overlays.spec.ts` asserts both overlays are absent and that
  the Settings gear takes the first click.

* **The FRAME budget card closed on its own anchors.** Both halves the card
  tracked are in the tree and pinned: `phase_usage_limits(declared_criteria)`
  scales the ceiling with the declared criteria between a floor and a cap,
  and `frame_result_from_draft` reports the bound criteria when a pass
  exhausts its budget instead of discarding them. The card's own text
  recorded both as closed; the "done when" holds, so the card leaves.

* **No module explains itself by what Kani did.** The two platform
  docstrings that still did (`tool_errors.py`, `pydantic_validation.py`) now
  state what the module owns; the rendered API pages carry no framework
  history.

* **The docs build imports three modules before Sphinx starts, and 40 pages
  gain their API.** `apps/api/docs/conf.py` imports `fastapi.openapi.models`,
  `langchain_core.messages` and `pathfinder.transport.http.schemas.sites` after
  it extends `sys.path`. Autodoc's type-comment pass writes the source text of
  `pydantic.BaseModel.__pydantic_extra__` back into `BaseModel.__annotations__`,
  which `ModelMetaclass.__new__` had cleared; pydantic then evaluates that
  string in the namespace of whatever model is built next, and a model with
  `extra="allow"` in a module without `Dict` raises `NameError: name 'Dict' is
  not defined`. FastAPI declares such a model, so every module that imports
  FastAPI failed. Building those three first removes the 40
  `autodoc: failed to import` warnings, and `docs/api/transport.rst` renders
  925 API objects across its 40 modules instead of prose with nothing under it.
  Sphinx 9.1.0 is the newest release and carries the pass; the reload the card
  blamed is gated on `SPHINX_AUTODOC_RELOAD_MODULES` and never ran. The
  reasoning and the two rejected alternatives are
  [a decision](decisions/extra-allow-models-are-built-before-autodoc-runs.md).

* **`sphinx.ext.napoleon` is on, so the tool reference shows each tool's whole
  contract.** The tool docstrings are Google style and the config had no
  extension that parses Google style, so every `Args:` block rendered as a
  block quote and lost the lines after the first indented continuation:
  `build_strategy`, `lookup_gene_records` and `search_for_searches` each
  published a truncated contract. Napoleon renders them as parameter lists and
  removes 13 of the 17 docutils warnings without touching a docstring, which
  matters because each of those strings is also the tool description the model
  reads. The remaining four, in two docstrings, are fixed as markup: the
  module docstring of `ai/graph/stream_events.py` escapes the plural after an inline literal (and
  becomes a raw string, so Python 3.14 does not warn on `\ `), and the example
  in `build_strategy` opens with `::` so its code is a literal block. No word
  in any docstring changed. `autodoc_inherit_docstrings` is off, so a
  third-party base class's prose is no longer published as this project's API;
  it was pulling `pydantic_settings`' `Args:` block into
  `TomlConfigSettingsSource.__init__` and taking an ambiguous `type`
  cross-reference with it.

* **`overview.rst` and `ai_functions.rst` describe the system that exists.**
  The overview is rewritten around the installed assistants, one chat turn
  (dispatcher, deferred `chat_turn` job, worker, two-node graph, durable event
  log), the Lead with FRAME, BUILD and VERIFY as tools, durable tools, the
  typed `data-*` parts, cross-thread memory and the layer rules; the Kani
  sections, the `subkani_*` event table, the delegation-plan grammar, the
  `@-mentions` block whose service no longer exists and the Redis dropdown are
  gone. `ai_functions.rst` is now the tool index by caller: Lead, FRAME, BUILD,
  VERIFY, EDA, the shared three, and the approval and durable mechanics.
  `conf.py` no longer resolves an intersphinx inventory at `kani.readthedocs.io`,
  and `grep -ri kani apps/api/docs` returns nothing. Two module docstrings
  still name the old framework and are published on `docs/api/platform.rst`;
  they are [a new card].
  With all three cards closed, `uv run sphinx-build -b html docs docs/_build/html` exits 0 with
  **3 warnings**, down from 73; all three are the one ambiguous `kind`
  cross-reference across the 13 classes that declare that attribute. Two
  docstrings that only became visible once their modules imported open a bullet
  list directly under a colon line, which docutils reads as an unexpected
  indentation: the module docstring of `ai/tools/standalone/optimization.py`
  and `dispatch` in `ai/conversation/dispatcher.py` each gained the blank line
  the list needs.

* **An `automodule::` target that names nothing now fails a test, not a page.**
  All 73 dangling targets are gone from `apps/api/docs/api/*.rst`: the ones
  whose module moved are repointed (`transport.http.sse` to `sse_utils`, the
  four `routers.strategies.*` to `routers.conversations.*`, `schemas.chat` to
  `schemas.conversations`, `schemas.strategies` to `schemas.strategy_ast`,
  `persistence.session` to `assistant_core.platform.db`,
  `services.experiment.core.streaming` to `services.experiment.streaming`, the
  four experiment enrichment modules to the `services.enrichment` package,
  `integrations.veupathdb.site_search` to `site_search_client`), and the ones
  whose surface is gone lost their prose with them (`platform.redis` and the
  Redis event-bus dropdown, `platform.events`, the seven
  `services.strategies.engine.*`, `domain.parameters.normalize`,
  `domain.strategy.compile`, the workbench-chat endpoint table). Three pages
  described a framework the product replaced: `agents.rst` is rewritten around
  the Lead and the FRAME, BUILD and VERIFY sub-agents, `chat.rst` around the
  dispatcher, the worker turn runner, the two-node graph and the durable event
  log, `tools.rst` around the phase toolsets and `ai/tools/standalone`;
  `engines.rst` and `delegation.rst` are deleted with their toctree entries and
  the two grid cards that linked them, and `ai.rst` is now the model page
  (catalog, resolution, settings, tiers, scripted model, pricing). The gate is
  `tests/unit/test_sphinx_automodule_targets_import.py`, which walks every
  `.rst` under `apps/api/docs`, extracts each target and imports it: it failed
  on 73 of the 241 targets before the change and passes on all 278 after.
  `sphinx-build` stays without `-W`, and its warning count falls from **108 to
  73**: no warning left says a module is missing. Three cards carry what
  remains, all of it outside the docs tree - 40 live modules autodoc cannot
  reload under Python 3.14 (`NameError: name 'Dict' is not defined`, raised
  re-executing `fastapi.openapi.models`), 17 tool docstrings written as plain
  text where the renderer wants reST, which truncate in the tool reference,
  and the Kani-era prose in `overview.rst` and `ai_functions.rst`, which carry
  no target for the new gate to reach.

* **The backend coverage gate was red on two tests that pass on their own,
  because a devtools library call routed the whole process's logs to stderr.**
  `uv run pytest --cov=src --cov-fail-under=40 -q` reported
  `2 failed, 4542 passed` on `test_memory_deadline.py::test_retrieval_degrades_to_no_memories`
  and `test_worker_heartbeat.py::test_a_wide_gap_is_reported`, both
  `assert '...' in ''` on `capsys.readouterr().out` with the warning text under
  "Captured stderr call"; the unit-only run was green, because the integration
  tier collects first. `devtools/chat.py::drive_run` and `run_respond` called
  `structlog.configure(logger_factory=PrintLoggerFactory(file=sys.stderr))`, so
  every integration test that drives a run left the process logging to the
  stderr object of that test. Routing the framework's logs is the command
  line's job: the call is now `route_framework_logs_to_stderr`, made once in
  `chat.main()` and once in `evals.main()`, and
  `test_run_once_leaves_the_global_logger_config_alone` compares
  `structlog.get_config()` across a driven run. The suite also restores the
  configuration around every test (`tests/conftest.py::_restored_logger_config`),
  and `tests/unit/test_global_logger_config_does_not_leak.py` reconfigures
  structlog in one test and reads the logger on stdout in the next. The second
  half of the same leak was the stdlib side: the app lifespan calls
  `setup_logging`, which appended a root handler bound to the stdout of the test
  that ran it - five root handlers after one run, and a later test's
  `capsys.readouterr().out` came back empty for `logging` output too. The
  lifespan test's `isolated_lifespan` fixture now patches `setup_logging` like
  every other dependency it isolates, and
  `test_the_lifespan_leaves_the_process_s_logging_alone` compares
  `logging.getLogger().handlers` across a lifespan run.

* **A misclassified imperative turned into a refusal with a false excuse, and
  two paid turns produced nothing.** "Yes, rerun the differential expression ...
  and then create the strategy step ..." and "Please run the differential
  expression now ... add the resulting genes ... as a step in my strategy." were
  both classified `follow_up_question`, so `intent_gate.hide_building_tools`
  removed the nine building tools and the Lead answered that "the analysis
  controls ... are not available in this turn. Please retry this request.";
  only a third message, classified `extend_strategy`, built. Two layers changed.
  `classify_user_intent` now states that an imperative to run, rerun, build, add
  or create - a bare "yes, do it" that accepts the assistant's own offer, and a
  retry after a failed task - is a building classification and never a
  `follow_up_question`. The Lead's rules now answer a missing building tool with
  `classify_user_intent` again as the FIRST action, and forbid both the
  unavailable-tool sentence and asking the user to retry. The gate was measured,
  not assumed: `test_a_corrected_classification_unhides_the_building_tools`
  drives a run whose first classification is `follow_up_question` and whose
  second is `extend_strategy`, and the step after the correction carries
  `build_strategy` and `edit_strategy`, because `PrepareTools` runs on every
  model step and reads `LeadDeps` live. The corpus case
  `an-assent-to-build-builds` is the counterpart of `question-turns-do-not-build`:
  an offer context, then the measured assent, and a persisted `GenesByTaxon`
  strategy. 8/8 cases pass under the deterministic provider.

## 2026-08-30

* **Turn-driving feature specs run serialized, and the e2e suite's last
  harness reds are fixed.** `apps/web/playwright.config.ts` splits the feature
  project in two: `feature-turns` carries the nineteen specs that send a
  message through the mock provider and waits on a turn, with
  `fullyParallel: false`, and `feature` ignores the same list, so
  `playwright test` still runs all 156 tests once. `auto-build`,
  `execution-phase` and `ai-workbench-integration` pass in the full run, and
  `fungal-pathogenesis` has its first green run since the fixme came off.
  Four specs reached `/conversation/<id>`, which is a 404 without the site
  segment; `eda-chat-parts` asked for "Open EDA" and "Open in EDA tab", which
  the vocabulary decision renamed to "Open Studies" and "Open study";
  `durable-progress-live` asked for a "Task completed" card the thread
  redesign replaced with a task row; `user-data` accepted a `seed_complete`
  frame that reported zero strategies, and now reads its counters;
  `toxoplasma-host-invasion` asserted a union preview while the compose bar
  still showed Intersect, and `expectComposeResultCount` is scoped to the
  sidebar that owns it; the two journeys that open with "I'm investigating"
  now assert the context-statement reply instead of the mock marker.
  `e2e/global-setup.ts` warms one request per route pattern before the run, so
  a spec no longer pays a route's first compile inside its own budget, which is
  what the Turbopack decision already prescribed: the first analysis spec on a
  restarted container goes from 1.4 min to 9.4 s. `makeWdkLinked` in
  `dismissed-strategies` read the conversation it had just created off the
  first sidebar row, which is a race with the refetch: under load both calls
  returned the same id, the test dismissed the conversation it meant to keep,
  and the end state was the other one still active. It reads the id from the
  route instead, through `openConversationId`.

* **The last module over the 400-line cap was split along its own seam.**
  `domain/parameters/values.py` 428 -> 197 meaningful lines: it owns the eleven
  `*Value` models, the filter clauses one of them carries, and the `ParamValue`
  union, and nothing else. `value_codec.py` (219) owns the translation: the wire
  and decoded payload builders, `from_wire`/`to_wire`, `from_decoded`/
  `to_decoded`, the maps over them, and the coercion of a raw scalar, list or
  dict into a typed value. `close_open_range` went to `canonicalize.py` (160),
  its only production caller and the module that already owns the spec-dependent
  post-processing, so the `ParamSpecLimits` Protocol that existed only to keep
  `values.py` from importing `specs.py` is deleted and the function takes
  `ParamSpecNormalized` directly. No re-export and no shim: 26 modules and 10
  test files import the module that defines the name, and the two rule anchors
  that pointed into the moved half (`WDK-MAP-001` at `_WIRE_BUILDERS`,
  `WDK-VOCAB-004` at `coerce_context_values`) point at `value_codec.py`.
  `check_max_lines.py` exits 0.

* **The workbench chat surface is deleted, not revived.** The eight experiment
  tools split out on 2026-08-30 had no importer outside their own island: no
  toolset named `refine_with_search`, `refine_with_gene_ids`,
  `re_evaluate_controls`, `fetch_result_records`, `lookup_gene_detail`,
  `get_attribute_distribution`, `compare_gene_groups` or `search_results`, and
  no agent was parameterised on `WorkbenchDeps`. Nine files go:
  `ai/tools/standalone/experiment_refinement.py` and `experiment_analysis.py`,
  `services/experiment/strategy_refinement.py`, `result_analysis.py`,
  `workbench_deps.py`, `ai_analysis_helpers.py` (reachable only from the two
  service halves), `ai/prompts/workbench_chat.py`, `ai/prompts/experiment/
  workbench.md`, and `tests/unit/services/experiment/
  test_split_experiment_tools.py`, whose 344 lines tested nothing else. The
  `"workbench"` entry left `_LOCAL_FILES` in `platform/langfuse/prompts.py`, so
  `seed_prompts()` no longer uploads a prompt nothing loads. Eight
  `vulture_whitelist.py` entries go with them, and the Sphinx pages stop
  describing an agent that does not exist: the `WorkbenchAgent` section in
  `docs/api/agents.rst` (it still named Kani and seven tool mixins), the
  `Workbench Chat` section and two schema/router automodules in
  `transport.rst`, the `AI Analysis` and `Strategy Refinement` sections in
  `experiments.rst`, and the prompt automodule in `ai.rst`. `apps/api/
  README.md` no longer lists a `services/workbench_chat/` directory. The audit
  that found those stale pages also found 73 other `automodule::` targets with
  no module behind them, recorded as its own card.

* **An eval case is a thread, and the corpus can now hold an edit.** `EvalCase`
  states `turns`, a list driven in order on one conversation id, and `prompt`
  is gone with no alias; the five shipped cases carry a one-entry list, so none
  of them changed what it asks. The expectation gained `stepIdsUnchanged`,
  observed from the persisted strategy's `wdkStepIds` on both sides of the last
  turn (a thread that held none before it observes `None`, so nothing passes
  vacuously), and `parameters`, which names per search the values that search
  must carry. Two cases were written from the closed edit defects and both were
  measured against live plasmodb through the deterministic model:
  `edit-keeps-the-criteria-it-was-told-to-keep` (build three criteria, then
  "swap the organism on the seed criterion and keep the rest") and
  `edit-does-not-mint-new-wdk-step-ids`. Each was shown to fail on a reverted
  guard and pass on the guard restored, both reverts byte for byte. Removing
  the pre-edit tree the commit diffs against (`commit.py`, `old_ast = None`)
  turned every step into a fresh WDK step: `stepIdsUnchanged: expected 'True',
  got 'False'`. Seeding the edit's FRAME draft with an empty spec instead of
  the spec the strategy already holds (`dispatch_context.py`) left the swap
  unapplied: `parameters.GenesByTaxon.organism: expected 'Plasmodium vivax
  P01', got 'Plasmodium falciparum 3D7'`, with parameter fidelity 0.5. Recorded
  as a measured limit: the shrink path the first case describes is closed by a
  refusal rather than by a value, so the case reads the swapped parameter, not
  the node count, to tell a landed edit from a refused one.

* **Eval scoring answers "how far", not only "same shape or not".**
  `pathfinder.evals.distance` implements the retired thesis decomposition in
  plain Python and adds no dependency: topology as a normalised Zhang-Shasha
  distance with the labels erased, search selection as a Jaccard distance over
  the search names, a labelled distance that charges 0.3 for a differing
  operator and up to 0.7 for parameter divergence, and parameter fidelity over
  the searches the two trees share. The two rows the item filed now separate:
  `((GenesByText UNION GenesByGoTerm) INTERSECT GenesByTaxon)` against the same
  tree with `INTERSECT` in place of `UNION` scores topology 0.0, searches 0.0,
  labelled 0.06; against `GenesByLocation` it scores 0.8, 1.0, 1.0. The
  expected side is parsed from the case's structure signature, so a case still
  states one readable string. Every case result carries the four numbers, on a
  pass as well as a failure. `zss`, `numpy` and `scipy` stay out of the API
  image: Zhang-Shasha is seventy lines, and pairing searches by name in
  postorder is already the optimal name-only alignment the Hungarian solver was
  there for. [The harness decision](decisions/the-eval-harness-is-pydantic-evals.md)
  records it and what it rejects.

* **Eval extraction keeps the first envelope of an id, as the client reducer
  does.** `read_turns` opened a turn at every user-message envelope, so a
  legacy conversation holding one duplicated envelope extracted a phantom turn
  with the request twice and the reply split across two turns. It now skips an
  envelope whose id the thread already carried; an envelope with no id still
  opens a turn, because one id names one message and no id names none. Pinned
  over the incident-shaped sequence: one duplicated envelope between two text
  deltas yields one turn, one request, and the joined reply.

* **The services layer holds no agent framework, and the vocabulary filter
  filters.** `services/experiment/ai_refinement_tools.py` and
  `ai_analysis_tools.py` imported `pydantic_ai.RunContext` inside services.
  They are split the way the four catalog tools were: the WDK halves are
  `services/experiment/strategy_refinement.py` and `result_analysis.py`, which
  take the site and the experiment by value and return typed models, and the
  `RunContext` halves are `ai/tools/standalone/experiment_refinement.py` and
  `experiment_analysis.py`. The import-linter contract that says services never
  import transport or AI now also forbids `pydantic_ai`, so the whole layer is
  covered rather than two entry points, and the contract was proved to bite by
  planting the import and reading the break. In `services/catalog/
  search_inspection.py` the `isinstance(vocab, dict)` branch is gone, because
  `WDKVocabulary` is a list or a `CamelModel` tree and never a dict; the filter
  now walks a tree and keeps the branches that reach a match, so a query on the
  `GenesByMolecularWeight` organism tree narrows 90 leaves to 25 and the
  rendered tree no longer offers `Plasmodium berghei ANKA` under `falciparum`.
  The list branch matched `str(term)`, the pydantic repr, so the query `root=`
  matched all 48 entries; it reads the term and the label now and matches none.

* **A stopped turn closes the tool calls it left open.** The error path
  already wrote `tool-output-error` for every open call; the stop path wrote
  only the stopped event, so a lead tool call interrupted by Stop stayed
  `input-available` and its trace row read as running forever. The cancel
  branch of the turn driver now closes every open call with "Stopped by the
  user.", pinned by a test that stops a turn mid-call and reads the closing
  chunk. The stub writer in that test now satisfies the writer protocol, and
  the last type suppression in the test tier went with it.

* **The small UI defects of the 2026-08-17 run are closed, and the three the
  e2e run measured with them.** Fixed: a refused request now reports what the
  server said, because `extractErrorMessage` reads `detail`, then each
  `errors[].message`, then `title`, so a plan refusal reads "Record type is
  required" rather than "HTTP 422 Unprocessable Content"; `streamTypedEvents`
  throws that same `APIError` instead of `stream failed: 403`; and the chat's
  failure notice runs the transport's rethrown body through `toUserMessage`.
  The status line and the Progress panel read the running phase off the same
  `data-sub-agent-call` chunks the trace reads (`runningPhase`), so neither can
  lag the card any more - `build_strategy` runs no sub-agent and sends no
  status label of its own. A Progress tab with nothing behind it raises no dot
  (`ledgerTabHasContent`). Every message action carries an `aria-label`. The
  rail panel overlays the chat below the width where the chat would be a
  sliver: at 866px with the list and a panel open the chat column is **54px**,
  so `shouldOverlayRailPanel` floats the panel instead. The thread's scroll
  surface is `ThreadPrimitive.Viewport`, whose `scrollToBottomOnRunStart`
  scrolls on send; `use-stick-to-bottom` is gone. Rail markers are keyed by
  conversation, so a fresh thread shows no Tasks dot. A finished task links to
  the turn that carries its result, from the card and from the Tasks panel row.
  The enrichment panel renders the analyses the API saved on the gene set and
  invalidates that query after a run, so a run's 200 reaches the page through
  the cache and a set the researcher returns to still shows its results. The
  Compose panel no longer promises a Venn it cannot draw: a set opened from a
  strategy stores no gene IDs, so `SetVenn` says that instead of captioning an
  empty area. `devIndicators: false` stops the dev overlay taking pointer
  events. `--chart-1`, `--chart-2` and `--chart-3` are darkened so a gene-set
  source badge reads at AA over its own tint - `--chart-3` measured **3.53:1**
  on a card and now measures **4.61:1** at worst, pinned for all four badge
  tokens in both grounds by `statusTokens.test.ts`. Shown not to reproduce: the
  workbench polls nothing (every one of `gene-sets`, `control-sets`,
  `me/quota` and `veupathdb/auth/status` resolves to a 30 s `staleTime` and no
  `refetchInterval`, pinned in `features/workbench/api/polling.test.ts`), and
  the phase card that stayed `started` after Stop is closed by the client's own
  reader rule. Moved, not dropped: inserting a saved strategy from an empty
  Strategy panel and the constraints a later turn forgets belong to the
  saved-strategy and accumulated-requirements work.

* **A vocabulary entry names its parent, and a search that cannot be read no
  longer reads as one that does not exist.** `WDKVocabTerm` is
  `tuple[str, str, str | None]` and exposes the third element as `parent`, which
  is what `EnumParamVocabInstance.getFullVocab` writes; the reference client
  types that column `null` and is wrong about its own platform
  (WDK-VOCAB-007, `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`). Before the change
  `GenesByOrthologPattern` failed with **1802 validation errors** on plasmodb and
  no route could read its parameters; after it the live document parses and
  `phyletic_tree_of` builds **903 nodes under 3 roots**, with
  `derive_binding(pfal, hsap)` giving `%hsap:N%pfal:Y%`. `PhyleticTree.from_vocab`
  now attaches a term to the parent it names and falls back to the indent stack
  only for a term that names none, and plasmodb and toxodb agree on all 903 rows
  that the indent depth is the parent's depth plus one. The failure that hid this
  is gone too: `_fallback_scan_record_types` answers a search WDK lists but cannot
  serve with `reading <search> failed: <cause>`, keeps `Search not found` for a
  name that is genuinely absent, and drops the search itself from its own
  did-you-mean.

* **The substitution report compares each parameter as what it states.** A filter
  is compared as its clause set - each clause by field, `isRange`,
  `includeUnknown` and its values as a set - so key order, clause order and a
  dropped `fieldDisplayName` no longer read as a value WDK chose. Measured on
  plasmodb: posting `variation_sample_meta` to `GenesByNgsSnps` with every other
  parameter bound returns `isValid: true` and echoes the caller's own string
  verbatim, while `FilterValue.to_wire` re-serializes it with the keys reordered
  and the display name gone, so the old text comparison reported the parameter as
  substituted. An `input-step` is now excluded by name: its value is the wiring
  the caller made, never a choice WDK made, and `canonicalize` says so where it
  skips it (WDK-PARAM-008 and WDK-PARAM-009,
  `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`).

* **A step carries its own record class, and the strategy's is the root's.**
  `StrategyStep.record_class` holds the record type WDK lists that step's search
  under; `assign_step_record_classes` fills it from the site catalog,
  `validate_parameters` reports the class it resolved, and the push addresses each
  step's search URL from the step's own rather than from one value per graph.
  `record_class_of` reads a step's class and takes a combine's from the steps it
  consumes, `sync_strategy_for_site` sets the strategy's class from the root through it,
  and the leaf-first `resolve_record_type_from_steps` is deleted along with the
  unreferenced `services/strategies/search_resolution.py`. The pin is live on
  plasmodb: `GenesByMolecularWeight` is listed under `transcript` and
  `GenesFromTranscripts` ("Transform Transcripts to Genes") under `gene`, and each
  404s under the other - `There is no search "GenesFromTranscripts" associated
  with record type "TranscriptRecordClass"`. **WDK-STRAT-004 (`veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`)
  is `ENFORCED`, and the bundle's `UNENFORCED` column is now empty**: 84 rules, 80
  enforced, 4 partial. The persisted AST gains no field, so there is no migration:
  the class is derived from the catalog on the push and the sync that use it.

* **The hidden-default sweep stops at published defaults, by ruling.** Measuring
  `channel` (75 searches) and `dataset_url` (56) needs a plausible value per
  search rather than a published one, which is 131 separate studies whose answer
  is a property of the datasets loaded that day. The sweep already names every
  outcome: `SweepReport.measured` carries one row per search with its status and
  WDK's own message, so the 58 that answer 500 are listed by name in the
  `wdk-hidden-defaults.json` the nightly lane uploads, and none of the 158
  refusals names a hidden parameter. Recorded as
  [the sweep stops at published defaults](decisions/hidden-default-sweep-stops-at-published-defaults.md)
  and linked from WDK-PARAM-010 (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`); no
  code changed.

* **The two EDA subset searches count the same genes; the 46 that separated
  them was transcripts against genes.** Measured on plasmodb.org on the same
  day with one analysis spec (`DS_53f554ec6a`, `VAR_035294d0` = "P. berghei"),
  `GenesByPhenotypeEdaSubset_PlasmoDB_Rod_Mal_Phenotype_RSRC` and
  `GenesByEdaSubset` both answered `totalCount` 5602 and `displayTotalCount`
  5556. The earlier 5602-against-5556 was one result read through two counts,
  and `estimatedSize` tracks the display one (WDK-FILTER-005). The model agrees:
  the two process queries are the same plugin with the same four `wsColumn`s,
  differing only in `visible="false"` on the dataset id. One real difference
  did turn up and is now documented with it: `eda_analysis_spec` declares no
  `allowEmpty`, the per-dataset template overrides it to true, and the generic
  search answers HTTP 422 "Cannot be empty." for an unfiltered analysis, where
  the per-dataset search answers 5810/5764. `eda-wdk-bridge.md` carries the
  table and the pinned model links.

* **"N genes analyzed" is the size of the set that went in.** `percentInResult`
  is result genes over background genes - the GO plugin's own `COLUMN_HELP`
  reads "Of the genes in the background with this term, the percent that are
  present in your result" - so inverting it returned a term's genome-wide
  count, and a 46-gene set read "217 genes analyzed". `derive_total_analyzed`
  is deleted; `EnrichmentService` reads the step's own count once per batch and
  every analysis reports it, and `parse_enrichment_from_raw` takes
  `analyzed_gene_count` because no plugin publishes a result-level total. The
  semantics and the measurement are recorded under WDK-ANS-007.

* **A scored comparison persists encoded parameters, and a failed scoring says
  so.** The single-mode branch of `_persist_experiment_strategy` handed typed
  `ParamValue`s to `WDKSearchConfig` and every variant died with seven
  validation errors; it now encodes with `encode_params`, like the tree branch
  four lines above. A variant that still fails carries one line naming the
  first rejected field rather than the validation dump, and every variant
  carries `control_hits`, the given control ids its result contains - read from
  the experiment when it ran, and from the variant's own answer when it did
  not - so "which threshold recovers these three genes" is answerable either
  way. The tool's summary and its docstring tell the Lead to report a failed
  scoring as one, and the card renders "scoring failed: <line>" with the
  membership beneath it.

* **A dispatch card ends in a terminal state (protocol 1.5.1).** Closing a
  phase card is a reader rule, not a chunk: `buildTrace` in
  `assistant-platform/packages/assistant-client-ts/src/core/trace.ts` resolves every dispatch its
  turn left `started` to `cancelled` when the parts carry `data-turn-stopped`,
  to `failed` when they carry `data-turn-failed`, and to `superseded` when the
  host says the turn ended and neither is there. Nothing the graph writes after
  a Stop reaches the log - the astream task is cancelled and only
  `turn_stopped_event()` follows - so the producer cannot close the card, and
  the error path left it `started` too. `TraceGroupState` grows `cancelled` and
  `superseded`, `BuildTraceOptions` grows `turnEnded`, `TraceAnchor` passes it
  for every message but the streaming one, and `TraceGroup` reads the two new
  states as "Stopped" and "Not finished". PROTOCOL.md states the rule beside
  the turn's shape in section 6.

* **A stopped turn stops spinning.** The same close reaches the rows: a call
  still running inside a dispatch the turn cancelled or failed reads the new
  `TraceRowStatus` member `stopped`, drawn with a still `CircleDashed` and the
  word its group carries ("Stopped" under a cancelled dispatch, "Not finished"
  under a failed one). `Trace.running` is therefore false, so the run reads its
  step count instead of "Working..." and collapses like any settled run. A
  `superseded` dispatch keeps its running rows and its spinner: the durable
  task really is still running, and the turn that resumes it settles the row.
  Measured before the fix on a stopped dispatch: group "Stopped", summary
  "Working...", glyph `animate-spin`, `aria-expanded` "true".

* **A checkpoint call is bounded by the turn.** `BoundedCheckpointCalls` in
  `assistant_core/conversation/checkpointer.py` wraps `aget_tuple`, `aput`,
  `aput_writes` and `adelete_thread` in `checkpoint_deadline`, an
  `asyncio.timeout` of `checkpoint_timeout_seconds` (default 30) that raises
  `CheckpointTimeoutError` naming the operation and the window;
  `lifespan_checkpointer` yields `BoundedPostgresSaver` and bounds its own
  `setup()`. The checkpointer was the last Postgres path of a turn with no
  bound: the same single `AsyncConnection` shape the memory store had, so a
  checkpoint read or write that never resolved held the turn and its worker
  slot. The turn reports the typed error through the `error` chunk and
  `data-turn-failed` its driver already writes. Pinned against a saver whose
  every call hangs, which now fails in under 1 s.

* **A turn cannot wait on the memory store without end.** Retrieval at Lead
  entry and the auto-write in `finalize_turn` run inside
  `memory_store_deadline`, an `asyncio.timeout` of
  `memory_store_timeout_seconds` (default 30). Retrieval logs the timeout and
  returns no memories; the auto-write logs and re-raises, so the turn writes
  `error`, `data-turn-failed`, `finish` and `done` instead of holding its
  worker slot. The store was the one outbound call of a turn with no bound:
  `AsyncBatchedBaseStore` awaits a future only its batch task resolves, over a
  single `AsyncConnection` with no statement timeout, and the unit test written
  against a store that never answers ran the full 600 s command ceiling before
  the deadline and 1.26 s after it. `lifespan_memory_store` now cancels and
  awaits that batch task before the connection closes, so a closed store leaves
  no `_run()` task pending at `langgraph/store/base/batch.py:330`. The FungiDB
  journey spec no longer carries `test.fixme`. Decision:
  [a-memory-store-call-is-bounded-by-the-turn](decisions/a-memory-store-call-is-bounded-by-the-turn.md).

* **A busy worker is not a dead one.** The worker's heartbeat moved off the
  event loop the jobs run on: `jobs/heartbeat.py::HeartbeatThread` refreshes
  `procrastinate_workers.last_heartbeat` from a thread with its own loop and
  its own connection every `worker_heartbeat_interval_seconds` (5), and warns
  when a beat lands more than three intervals after the last one. `amain`
  builds the `procrastinate.worker.Worker` itself, because the thread needs the
  worker id the worker registers. Measured with one job holding the loop for
  5.00 s: a beat on that loop lands 0 times and the row reads 5.028 s old,
  while the thread beats 10 times and the row reads 0.315 s old.
  `worker_dead_heartbeat_seconds` therefore drops from 300 s to 60 s, so a
  killed worker's thread unlocks in one to two minutes. On the web,
  `notReady == ["worker"]` renders the app behind a non-blocking banner
  instead of the fatal "Some services failed to start" page, and without
  waiting out the startup grace window. Decision:
  [a-dead-worker-fails-its-turn-by-heartbeat](decisions/a-dead-worker-fails-its-turn-by-heartbeat.md).

* **The agent can start from a strategy the user saved.** FRAME has
  `list_saved_strategies`, a service read of the caller's saved threads on the
  current site (name, thread id, WDK id, record type, root count, step count),
  and `set_criterion(saved_strategy=...)` binds a criterion to one instead of to
  a search. The criterion carries the saved strategy's steps, cloned with fresh
  ids by the same `clone_saved_strategy` the panel's "Insert saved here" runs,
  so the FRAME to BUILD conversion splices the subtree with no I/O: a saved
  operand moves to the combine's secondary input, where WDK marks the collapsed
  reference, and MINUS mirrors to RMINUS when it moves. A reference the listing
  does not hold records an open `saved_strategy` slot before the retry that
  names the listing, so `ready_to_build` stays false and `drop_criterion`
  refuses that criterion: the measured failure was a frame that dropped the
  saved input and built `GenesWithSignalPeptide` alone for 603 genes. On the
  web, `POST /conversations/{id}/insert-saved` accepts an empty `targetStepId`
  and makes the saved strategy the thread's root, which is what the empty
  Strategy panel's new "Insert saved strategy" action and the Saved strategies
  page's "Use in new chat" both call. Decision:
  [a-saved-strategy-is-a-criterion-input](decisions/a-saved-strategy-is-a-criterion-input.md).

* **Building is a response to a request.** `IntentClassification` gains
  `context_statement` and `memory_request`, and a `PrepareTools` capability on
  the Lead drops `frame_problem`, `build_strategy`, `edit_strategy`,
  `recover_failed_steps`, `verify_strategy`, `open_eda_analysis`,
  `set_eda_filters`, `run_eda_compute` and `create_eda_step` from the tool list
  on every turn whose classification is not one of the six that ask for a
  change. `remember` is now a Lead tool and stays visible in every intent, and
  a turn whose classification does not build contributes no strategy memory.
  The deterministic provider classifies once per turn, with a remember arc and
  a context-statement arc; the eval corpus gains
  `question-turns-do-not-build`. The classifier's constraint-kind list is
  derived from `ConstraintKind`, so `percentile` reaches it without a hand
  edit, and the tool tells the model to capture a stated share as that kind.
  Decision:
  [building-is-a-response-to-a-request](decisions/building-is-a-response-to-a-request.md).

* **A clarification adds to the request instead of replacing it.**
  `StrategyDomainState` gains `requirements`, the thread's stated constraints
  deduped on kind AND value, and `original_request`, the text of the first turn
  that stated a request of its own. `classify_user_intent` records both. The
  ledger's constraint section merges the whole accumulated list and the pinned
  summary prints one line per stated requirement, and `framing_goal` seeds a
  missing spec's goal with the original request followed by the clarification,
  so a clarification turn frames from both. Decision:
  [a-clarification-adds-to-the-request](decisions/a-clarification-adds-to-the-request.md).

* **An assumed value is recorded, not narrated.** `set_criterion` takes
  `assumed`, one entry per parameter whose value the criterion text does not
  state and that is not the sheet's default, with the value and one sentence of
  reason. The entries land on `Criterion.assumptions` and the ledger's
  constraint section renders each as a non-blocking `assumed` constraint,
  grounded, with the reason as its note, so the Lead names them from the ledger
  and the user can override any of them. Three refusals guard the input: an
  unknown parameter, a parameter this call left null, and a half of a reference
  and comparison pair, which has no defensible assumption. FRAME's instructions
  say when to declare one. Decision:
  [an-assumed-value-is-recorded-not-narrated](decisions/an-assumed-value-is-recorded-not-narrated.md).

* **A stated share is now checked against the percentile that was bound.**
  `ConstraintKind.PERCENTILE` carries a share and a direction ("top 10%"), and
  `ground_constraints` reads the criterion's `*percentile*` parameter from the
  values the spec bound: a minimum of 90 for "top 10%" grounds, a minimum of 80
  grounds SUBSTITUTED with the note "bound 80 means top 20%", which blocks
  because the constraint is user-explicit. `ground_constraints` therefore takes
  `param_values` beside `param_names`. VERIFY's instructions add that a numeric
  parameter is restated ONLY from its `constraint_report` entry, so a reply
  cannot write an interpretation the bound value does not support, and the
  verification prompt is ASCII throughout.

* **A search overview no longer carries a verdict nothing writes.**
  `SearchOverview` kept `decided`, `selection_status`, `rationale`,
  `selection_reason`, `confidence` and `param_hints`, whose only writer was an
  unregistered tool that is already deleted, so every reader ran against the
  default. The six fields are gone with `SearchSelectionStatus`,
  `AgentToolState.decided_search_names()` and `selected_search_names()`.
  `search_for_searches` and `list_searches` no longer drop a result or append
  the "already-decided search(es) hidden" note, the pinned discovered-searches
  instruction no longer prints a `[selected]` / `[rejected]` tag or a
  confidence, and the verification toolset's enum override keeps only the
  `wdk_step_id` constraint it can fill.

* **The last two modules over the 400-line cap were split along their own
  seams.** `frame_spec.py` 407 -> 370 meaningful lines, beside
  `frame_structure.py`, which owns the other half of an operational spec: the
  tree `set_structure` folds the bound criteria into. The module also drops its
  second copy of `CriterionRole` and reads the domain's. `conversation.py`
  413 -> 292, beside `saved_strategy.py`, whose `SavedStrategyRepository` owns
  the reads keyed by the WDK strategy a thread holds: the saved listing, the
  threads that import one, and the prune of threads whose WDK strategy is gone.
  `ConversationService` reaches those through
  `strategy_ops.list_saved_strategy_consumers`, so the delete guard keeps one
  owner for that query. No re-export and no shim: every caller and test imports
  the module that defines the name. `check_max_lines.py` exits 0.

* **The two modules the revision history grew past the 400-line cap were split
  the same way as the eleven before them.** `fork.py` 474 -> 165 meaningful
  lines, beside `fork_ids.py` (the fork's one id space and the chunk rewriting
  that moves a copied chunk into it), `fork_copy.py` (the event rows and the
  checkpoint rows) and `fork_strategy.py` (the anchor's snapshot and the
  strategy the fork pushes from it); `turn_runner.py` 425 -> 370, beside
  `turn_stop.py`, which owns the Stop path: the cancellation poll, the revision
  the thread opens on, and the restore a stopped turn ends with. No re-export
  and no shim, so a caller imports the module that defines the name, and the
  mechanic the earlier batches recorded held again: a monkeypatched global stays
  in the module the test patches, which moved
  `monkeypatch.setattr(fork_module, "materialize_strategy_snapshot", ...)` onto
  `fork_strategy` and the cancel-watcher patch onto `turn_runner.watch_for_cancel`.
  `check_max_lines.py` exits 0.

* **A strategy now has a revision history, and fork, revert and Stop read
  it.** Every write of `conversation_strategies` appends a `strategy_revisions`
  row through `ConversationRepository`, carrying the `strategy_revision`
  fingerprint, the full AST with its per-step WDK ids and counts, the record
  type, the step count, the WDK strategy id, the name and the message the turn
  ended with. A branch resolves the anchor message's snapshot and pushes that
  tree to WDK as a strategy of its own instead of duplicating the thread's
  current one, so a branch at the turn-2 answer opens on three steps rather
  than the four a later turn built; WDK's `sourceStrategySignature` duplication
  went with the code that used it. A thread with a strategy and no history is
  refused with `FORK_REFUSED` (409) rather than copied, and a branch is refused
  while a durable task runs in the copied prefix. Revert restores the snapshot
  in force at its target, or clears the strategy when the target predates every
  snapshot. A stopped turn deletes what it appended and restores the snapshot
  the thread opened with, or clears a first build that never reached WDK, and
  the epilogue's `data-strategy-revision` reports the restored state right
  after `data-turn-stopped`. A branch now keeps one id space: every copied
  chunk's `messageId`, `message.id` and `turn_id` go through the id map its
  `messages` rows are minted from, copied rows carry `task_id = NULL` so a
  parent revert or delete cannot cascade into the branch's log, and the branch
  copies its source's `assistant_id` and `application_id`. Migration
  `2026_08_30_0003`. The stopped build's phase card and the editor's rendering
  of a validation failure are the two halves of that report this change does
  not reach; both are closed by later entries under this date.
  Decision:
  [a-strategy-has-a-revision-history](decisions/a-strategy-has-a-revision-history.md).

* **Revert now truncates the thread the reader sees.** The revert flow
  invalidated `["conversations", <id>, "messages"]`, a key no query uses, so the
  snapshot query (`["conversations", <id>, "snapshot"]`) never refetched and the
  remount replayed the pre-revert list: the deleted turn stayed on screen with
  the edited message appended under it. The flow now invalidates the snapshot
  query and awaits it, so the client holds the re-snapshotted log before the
  edit is sent. The "Edit earlier message" dialog gained an error line: a failed
  revert or branch renders the server's refusal, the dialog stays open and both
  buttons stay clickable, replacing a toast the dialog covered. `toUserMessage`
  reads a problem body's `title` when it carries no `detail`, which is the shape
  `http_exception_handler` sends, so a 404 reads "Target message not found"
  instead of "HTTP 404 Not Found"; the hand-rolled `isProblemDetail` guard and
  the `isRecord` helper it was the last caller of are deleted. Pinned by
  `apps/web/src/features/conversation/RevertFlow.test.tsx`, which drives the
  real thread over a mocked transport.

* **`packages/shared-ts` now has a formatting gate of its own.** `types.ts` was
  prettier-dirty on the trunk and nothing read it: the `prettier-web` hook
  triggers on that package but runs `prettier --check .` inside `apps/web`.
  The package gains `format`/`format:check` scripts, a `prettier-shared-ts`
  pre-commit hook and a CI step in `check-shared-ts`. The two identical
  `.prettierrc.json` copies in `apps/web` and `assistant-platform/packages/assistant-client-ts`
  are replaced by one at the repository root, which every package resolves.
  The package's `lint` script named an eslint it does not install and nothing
  ran it; it is gone.

* **The ledger's sub-agent call counts had no writer and are gone.**
  `InvestigationLedger.sub_agent_calls_this_turn` and `sub_agent_calls_total`
  were never assigned by `derive_ledger` or anything else, so every
  `data-ledger-update` carried an empty list and a zero while a sub-agent ran,
  and the Lead's pinned summary read `## Sub-agent calls this turn: 0` over a
  live dispatch. The thread already records each dispatch as a
  `data-sub-agent-call` part, so the counts are deleted rather than given a
  writer: the two fields, the summary line, `SubAgentCallRecord`, the
  `subAgentCallsThisTurn`/`subAgentCallsTotal` members of
  `DataLedgerUpdatePayload`, the panel's `SubAgentCountSection` and the golden
  SSE fixture's keys. Pinned in `test_types.py` and `LedgerPanel.test.tsx`.

* **Batch 1's re-verification closed three gaps the batch had opened.** The
  `dev-login` credential kind reached `Principal` without the spec, so the
  OpenAPI check was red; the spec and the generated types are regenerated. The
  refresh route relinked every dev-login session to the account the shared
  VEuPathDB token names, which split one Playwright worker across two users on
  every page load; a dev-login session now returns from refresh untouched,
  pinned in `test_refresh_relinks_the_internal_session.py`. The Lead's EDA loop
  ended at `create_eda_step`, so a study-backed strategy was reported from the
  compute summary and never verified; the loop now ends with `verify_strategy`,
  pinned in `test_eda_instructions.py`. Two wasted retries per consultation came
  from the Lead placing background at the top level of `consult_user`; the tool
  now says background belongs to a question's `context`, and its schema is
  pinned to `questions` alone. The second pass then reached the frozen thread
  acceptance journey, which still expected the old trace-row labels (`Search
  eda studies`, `Open eda analysis`, `Search catalog`, `Set criterion`,
  `Preview eda subset`); the vocabulary decision wins, and the spec now
  expects `Find studies`, `Open study`, `Find searches`, `Choose a search` and
  `Preview samples`.

* **The CI, lint, size and build gates now report the code rather than
  themselves.** Seven backlog cards left together and one shrank. `yarn
  format:check` was already green on the trunk, so the formatting card left on
  proof rather than on a reformat; what stayed wrong was that the `prettier-web`
  and `prettier-assistant-client` pre-commit hooks ran `yarn format`, which
  writes, while CI ran `yarn format:check`, which reads. Both hooks now check,
  and CLAUDE.md's frontend list is the five package scripts CI runs, so a gate
  spelled one way in three places cannot pass in one and fail in another.

  `yarn lint` died at the 4 GiB default heap after 210 s with 3.93 GB resident
  and "Ineffective mark-compacts near heap limit". The lint program was reading
  8029 TypeScript files under `.stryker-tmp`, against 1002 under `src`: eight
  sandbox copies of the project that a mutation run leaves behind, each with its
  own tsconfig, each becoming another type-aware program. `.stryker-tmp` and
  `reports` join the eslint ignore set, and the same command now exits 0 in
  42 s at 1.96 GB. An ESLint-API test asks the config whether each generated
  tree is ignored, so the next such directory fails a test instead of a runner.

  `ruff check .` was red on an S608 in the tenancy migration, which built its
  copy statement by interpolating a table name and a column list into a string.
  The statement is now a SQLAlchemy `insert().from_select()` over a `sa.table()`
  built from the catalog's own column names, with `add`, `cut` and `old_like` as
  bind parameters and `to_regclass` taking its qualified name as one; the seven
  migration tests that drive the real database in both directions are unchanged
  and green. `pip-audit` reported 24 advisories across 13 packages, all with a
  fix version: the two pinned checkpoint packages moved
  (`langgraph-checkpoint-postgres` 3.0.5 -> 3.1.1, PYSEC-2026-3635), two direct
  dependencies gained a floor, and the remaining transitives are bounded in
  `[tool.uv] constraint-dependencies` with the advisory id on each line. It
  reports no known vulnerabilities. No advisory needed an ignore.

  The two locks disagreed on `langgraph-checkpoint` (4.0.1 against 4.2.0), and
  also on `langgraph-prebuilt` and `langgraph-sdk`, so the package suite proved
  decode behaviour the app never ran. `assistant-core` owns the checkpoint
  serializer, so it now owns the pin: `langgraph-checkpoint==4.2.0` sits in its
  dependencies and `apps/api` inherits it through the editable path dependency
  it already declares. A test reads both `uv.lock` files and fails when any
  shared `langgraph-*` package resolves to two versions.

  The last five modules over the 400-line cap were split the same way, so
  `check_max_lines.py` now exits 0 and `file-size-api` fails only for the change
  that grew a module: `domain/eda.py` 669 -> 129 beside the study tree it walks,
  the per-entry filter checks and the compute config; `eda_analysis.py` 467 ->
  308 beside the filter sheet and the guidance a result carries;
  `sub_agent_stream.py` 449 -> 263 beside the inner events it renders;
  `ledger.py` 424 -> 143 beside its four sections and their full renderers;
  `sub_agent_dispatch.py` 407 -> 353 beside the deps, the call id and the two
  early ends a dispatch shares with the edit dispatch. Ten modules across the
  two batches, and the two mechanics the first batch recorded held for all of
  them: the tool-summary walk follows a helper a tool's module imports, so the
  three EDA tools keep their `with_summary` calls in the module the walk starts
  from, and a monkeypatched global stays in the module the test patches, which
  pins `stream_sub_agent` and `build_strategy_from_spec` to
  `sub_agent_dispatch.py` and every name the EDA tool tests patch to
  `eda_analysis.py`. The frozen acceptance suite reaches `validate_filters` and
  `find_gene_entity` through `pathfinder.domain.eda`, so both stay defined there
  rather than re-exported.

  Six modules over the 400-line cap were split by responsibility, with no
  re-export shim and no behaviour change: `param_dag.py` 649 -> 237 beside a
  binding module and a filter module; `frame_spec.py` 600 -> 314 beside its
  proposals and its sheet; `strategy.py` 532 -> 203 beside the per-step edits
  and the refusals both halves return; `mcp/server.py` 488 -> 148 beside the
  catalog tools and the user-credentialed tools; `operations/apply.py` 458 ->
  230 beside the delete resolutions and the wiring primitives;
  `step_wdk_push.py` 416 -> 296 beside the WDK calls that create or patch one
  step. Two mechanics surfaced and are recorded on the card that remains: the
  tool-summary walk read a tool's own module only and now follows a helper the
  module imports, and a name a consumer reaches through a module rather than
  from its definition needs that module to declare it in `__all__` or
  `mypy --strict` calls it an implicit re-export. Five modules are still over
  the cap, in trees this work does not own, so the card stays and names them.

  `yarn generate:types` dumped the spec from whichever api container happened to
  be running, so a regeneration during an e2e session committed
  `/api/v1/dev/login` into the shared contract. It now builds the app in process
  with the production route set, and the writer refuses a spec that names any
  path the dev router mounts, reading that set off the router rather than a
  literal. Regenerating changed `packages/spec/openapi.json` and no generated
  TypeScript file: 1068 files came back byte-identical.

  The rule that Turbopack buffers SSE is retired on measurement rather than on
  belief. A proxied `text/event-stream` emitting five frames 300 ms apart
  reaches the client through a Next 16.2.0 dev server with its gaps intact under
  both bundlers - 0.271, 0.302, 0.311 and 0.303 s under Turbopack. The dev
  script, the Dockerfile, CLAUDE.md and the batch-7 plan all name plain
  `next dev`, and [the decision](decisions/the-dev-server-runs-turbopack.md)
  records what was rejected. Turbopack's first frame is later by the on-demand
  compile, which is a cold start and is warmed, not timed out.

  Last, the injection scanner. `warm_up_piguard` built a `PIGuardScanner` and
  threw it away, so readiness primed the page cache and the first real request
  still built an onnxruntime session inside the 5 s enqueue wait - and in a test
  process, which never runs readiness, the red landed on whichever test posted
  first. The warm-up now loads the scanner the request path calls, the dead
  loader is gone, and a session-scoped fixture warms it once per test process
  the way readiness does in production. The 1.2 s bound the card flagged beside
  it no longer exists in the tree.

* **The test gates that could not decide anything now decide.** Five backlog
  cards left together. Both frontend ratchets are green on the trunk and run in
  CI beside `check:boundaries`: 84 tests gained an assertion on a value, and
  the weak-assertion baseline dropped from 209 entries to 62 as the fixed ones
  left it. Two more of the reported 86 were the script's own gap -
  `toBeEmptyDOMElement` was missing from its strong list - and the list gained
  it rather than the tests losing a good matcher.

  The checker also learned what a throwing query is. `getBy*` and `getAllBy*`
  raise when nothing matches, so `expect(screen.getByText("3.48"))` pins the
  value before any matcher runs, and calling that test weak asked its author to
  restate a literal the query already carried. Given a string or regex literal
  as the query's first argument the chain now counts as strong; a variable does
  not, and `queryBy*` and `findBy*` do not, because neither raises. That single
  rule cleared 126 of the 188 baseline entries, which is how many of them were
  never weak. The checker now has a checker,
  `scripts/check-weak-assertions.test.mjs`, in the shape the knowledge and WDK
  rule checkers already use, and it runs in CI.

  Every `.first()` and `.nth()`
  in the six older specs is now a locator that names what it means to click:
  the ensemble chip by its gene set's name, the gene set card by the `title`
  its name span carries, the branch button inside the assistant reply that
  carries it, and the task progress row inside the task that started it. Two
  page objects lost the same escape, because the specs that call them depend on
  it.

  Two api tests reported a machine's load as a product defect. The parallel
  fan-out test now counts the trials in flight and asserts five, rather than
  timing them against a 1.2 s bound that measured 1.47 s at load average 69.
  The deadlines that stand for "the turn finished" are named ceilings on a
  deadlock, and `db_cleaner` drains the turn it is about to truncate under, so
  a slow turn can no longer write an event for a conversation the teardown has
  already removed. Both hold at load average 80.

  `parse_sse_body` splits on `\n` alone. `str.splitlines()` also breaks on
  U+2028, which a recorded EDA study description carries, so a
  `tool-output-available` frame parsed in two while the wire frame was intact.

  The opt-in llm tier is gone. It had no test files at all - a conftest of
  fixtures for three models (`ClarificationQuestion`, `ProblemFrame`,
  `ResearchNote`) that no longer exist anywhere - so there was nothing to
  repair. A collect with `addopts` cleared now runs in CI and in the documented
  backend ladder, so the next tier that stops importing is reported by the only
  command that can see it.

* **Verification can now reach a verdict, and cannot state one the build does
  not support.** Three backlog cards left together. A tool that takes a graph
  id now answers to the VEuPathDB strategy id as well
  (`ai/tools/standalone/_validation_helpers.py::get_graph` resolves it through
  the session's `wdk_strategy_id`), so the lookup that returned "not found" on
  strategy 330558093 returns the graph. A study step is verified by its own
  numbers: `check_study_step` reads the volcano cut out of the step's
  `eda_analysis_spec` through `services/eda/export.py::exported_thresholds`
  and reports one `ConstraintCheck` per threshold the caller names, so the
  measured step reports 1,543 records at 2-fold and p 0.05 with `success true`
  instead of "should be treated as unverified".

  A success digest is now held to the ledger. `run_verification` derives the
  ledger and refuses a `success=True` digest that the build does not support -
  a build that failed, skipped or left a step empty, or a turn that built
  nothing on a strategy with no step in VEuPathDB - and rewrites it into a
  failure digest naming the contradiction. Rewriting at the single write point
  was chosen over a `ModelRetry` on the sub-agent
  (`decisions/the-ledger-outranks-the-verification-digest.md`): retries are
  finite, and the flag also decides the memory auto-write and the eval
  extractor's verdict, so the correction belongs where the digest is recorded.

  The verification playbook now picks its checks from what the turn changed.
  `VerificationScope` carries the turn's spec diff into the sub-agent's deps
  and the verification toolset filters `run_gene_set_enrichment` out of an
  edit that touched one criterion, so "add a P. vivax ortholog transform" is
  answered by a count check rather than a two-minute background job. The Lead
  passes `enrichmentRequested` when the user asked for enrichment by name.

* **One account's EDA authorization answered every later account in the same
  api or worker process.** `services/eda/catalog.py::_permissions` kept the
  `/eda/permissions` answer in a per-site cache, and `/eda/permissions` is an
  account-scoped read: it decides which datasets exist for the caller, which
  can be subset and which can export rows. The first credential to ask on a
  site decided what every later one was told, and `resolve_dataset` raised
  `UnknownEdaDatasetError` from the same map, so an account could be refused a
  dataset it owns or offered one it may not read.

  The entry is now addressed by the site and a sha256 of the request's
  VEuPathDB token, and a call carrying no token is refused before the address
  is built. `studies` stays keyed by the site, because the listing is the same
  for every account. Keying by the numeric WDK user id was rejected
  (`decisions/the-eda-permissions-cache-is-keyed-by-the-credential.md`): the
  `/users/current` round trip buys only the dedup of two tokens belonging to
  one account, and it would put a WDK dependency in a read that is otherwise
  pure EDA. `clear_study_caches` keeps its callers and now drops the new map
  too.

* **The turn that answered a durable call ran on the configured tier, not on
  the model the request pinned.** `jobs/runner.py` built
  `ChatRequestBody(conversation_id=...)` and nothing else, so
  `phase_models` and `phase_reasoning` were empty on the completion turn and
  `resolve_lead_model_context` fell through to the phase tier. The half of an
  investigation a researcher reads the compute numbers from was answered by a
  different model, at a different price, with nothing on the transcript saying
  so.

  The picks now travel on the durable task. `run_turn` publishes the validated
  pair on `phase_overrides_ctx`, `create_background_task` writes it to the new
  `background_tasks.phase_overrides` column (migration `2026_08_30_0002`), and
  `jobs/runner.py::_completion_body` rebuilds the completion turn's request
  body from the row. `BackgroundTaskRepository.create` takes a
  `NewBackgroundTask` spec, so the picks are a named field rather than a
  seventh keyword. Persisting them on the conversation was rejected
  (`decisions/a-durable-task-carries-the-turn-s-phase-picks.md`), because it
  would make a per-request override a thread setting.

* **A durable task's completion replayed the Lead node from its first line, so
  one prompt produced two EDA analyses, three compute jobs and no step.**
  `@durable_tool` called LangGraph `interrupt()` from inside the tool, inside
  the agent run, inside the `lead` node, and the worker resumed with
  `Command(resume=...)`. LangGraph re-executes a resumed node from its start:
  the model was called again, a second analysis was opened, `run_eda_compute`
  deferred a second job before its `interrupt()` returned the stored result,
  and `create_eda_step` failed twice on an analysis that carried no
  computation. The turn never wrote `done`.

  A durable tool is now a deferred tool. The decorator creates the
  `background_tasks` row with the pydantic-ai `tool_call_id` it will be
  answered on (new nullable column, migration `2026_08_30_0001`, which also
  flushes the interrupt-era checkpoints), defers the job, records a
  `DurableDeferral` on the deps, emits `data-background-task-started` and
  raises `CallDeferred`. The turn parks a `PendingDurableCall` beside
  `pending_approval` and closes. On completion the worker announces
  `data-task-completed` and opens a new turn with
  `TurnRequest(durable_result=...)`, which resumes the parked run with
  `DeferredToolResults(calls={tool_call_id: ToolReturn(...)})`; the tool's
  `chunks_from_result` runs there and rides the result's metadata, so the
  summary and the figure land beside the tool's output part. A durable call
  inside the verify sub-agent parks the dispatch with that run's
  `messages_json` and the completion turn re-enters it, so the verification
  verdict reaches the reply. `_resume_graph`, `_interrupt_chunks` and the
  `interrupt` import are deleted, and the turn runner reads `custom` chunks
  alone. The observable wire did not move, so PROTOCOL 6.1 stands.

* **One PathFinder session wrote two EDA analyses under WDK user 1216062453 and
  then read them back as WDK user 1202189953, which answered
  `GET /users/1202189953/analyses/PlasmoDB/Vd6RDIz -> HTTP 403`.** The
  `pathfinder-auth` cookie and the `Authorization` cookie are independent: the
  worker created the analyses with the token the tab carried at dispatch, a
  second VEuPathDB sign-in replaced that token, and the next read ran as the
  other account. Nothing compared the two: `require_registered_wdk_identity`
  asked only whether the token was registered, and `refresh_internal_auth`
  returned early on any `pathfinder-auth` cookie that decoded, so it could never
  relink.

  `services/wdk_identity.py::require_session_matches_wdk_identity` resolves the
  request's token through the cached `resolve_veupathdb_user_id` and raises the
  new 401 `WDK_IDENTITY_MISMATCH` when the internal user differs from the
  session's. The route gate runs it after the login check, and
  `resolve_chat_assistant` runs it for an assistant that declares an identity
  gate, so a mismatched turn is refused before a `chat_turn` job is deferred.
  A token that resolves to nobody is an outage, not a second account, and passes.
  The refresh route now resolves the token's account on every call and mints the
  new internal token when it differs. On the web, `wdkAuthRefusal` reads both
  codes and `handleWdkAuthRefusal` calls the refresh once for a burst and retries
  before it offers the sign-in prompt. The EDA 403 hint is path-aware: a path
  under `/users/` names ownership, not the study-id trap.

* **A model-written `eda_analysis_spec` reached WDK, and every report on that
  step answered `JSONObject["studyId"] not found`.** One conversation held a
  step on `GenesByRNASeq...Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq` whose
  spec parameter read `{"data_type":"read counts","comparison":{...},
  "fold_change":{...},"adjusted_p_value":{...}}` - a document the model
  invented, not an EDA analysis. WDK stores that parameter as a string and
  validates nothing, so the step was created and every `reports/standard` on it
  answered HTTP 400; verification could not read the gene set, and the
  researcher was told the result remains unverified. Prose in the Lead
  instructions was the only defence, and `EdaStepRequest` guarded the
  `create_eda_step` path alone, so `set_criterion` and the four other callers of
  `validate_parameters` accepted any string.

  `validate_parameters` is the one seam every build path crosses, so the check
  lives there. `EdaStepRequest` moved from `services/eda/authoring.py` to
  `services/catalog/eda_backed.py`, beside the two parameter names and the
  guidance it is judged against, and `check_eda_parameters` refuses a value that
  does not parse as an `EdaNewAnalysis` naming the same dataset. An empty spec
  stays valid for a search that is not compute-backed and is refused for one
  that is, because that plugin exports what a computation ranks. The refusal
  carries `eda_backed_guidance` as its detail, so the FRAME retry names
  `open_eda_analysis`, `set_eda_filters`, `run_eda_compute` and
  `create_eda_step` instead of repeating the rejection, and the declarative
  build fails the node before `push_step_to_wdk` is reached.

* **No internal name reaches the researcher.** The first real session showed
  `Open in EDA tab`, `Search eda studies`, a group labelled `Frame`, rail tabs
  `Ledger` and `EDA`, a badge `WDK` and summaries carrying `DS_e973eadd57`.
  `docs/knowledge/decisions/user-facing-vocabulary.md` fixes the glossary
  (study, Studies, Open study; VEuPathDB; Planning, Building, Checking,
  Repairing; Assistant; Progress) and two source scans enforce it: a vitest
  over every JSX text and string literal the app renders, and a pytest over
  every summary line, error title and detail, and refusal message in the
  study tools and services. All 81 registered tools carry a verb in
  `toolNames.ts`, so the Title-case fallback can no longer print a tool's
  internal name; the Lead's instructions carry the same rule for its prose
  and its consult questions. The recorded turn, the rail, the settings page
  and a live turn's prose scan clean.

* **The EDA tab's compute never landed on the analysis, and the consult recap
  could not read the answer it was given.** Running the differential
  expression from the tab answered `PATCH .../eda -> 200` four times and then
  `POST /api/v1/eda/viz -> 409: Analysis HBQKQbX carries no compute`: the
  route submitted the job and never wrote the computation into the analysis
  document, which is the SSOT the volcano reader checks, while the chat path
  already did through `apply_computation`. `run_analysis_compute` now reads
  the document once, applies the computation only when it is missing or
  different (which is also where a study-rejected config is refused before
  any job starts), and submits; a poll tick writes nothing. Route tests pin
  compute-then-volcano and the single write. The recap showed `-` for an
  answered question because pydantic-ai dumps a tool return without aliases:
  the answer reached the log as `question_id`/`chosen_labels` while the
  protocol names `questionId`/`chosenLabels`. `UserQuestionAnswer` now
  serializes by alias; an adapter test pins the wire names, and the recap's
  arrow and placeholder are ASCII. Threads answered before this stay
  snake_case in the log and still show the placeholder; no dual-casing reader
  was added, because a tolerant reader would hide the next mismatch.

* **A real turn drew six one-row traces instead of one, and the cause was an
  empty reasoning part before every tool call.** The first prompt run against
  the redesigned thread on the real provider (the heat shock RNA-seq study,
  febrile versus normal) showed `1 step` six times in a column. The durable
  log for that turn holds eight `reasoning-start`/`reasoning-end` pairs with
  zero `reasoning-delta` between them, one before each call: the model's
  reasoning item carries an empty summary, the adapter emits the part anyway,
  and `buildTrace` rule 1 closed the run on every `reasoning` part. Two fixes,
  each pinned. The grouping rule now says only a `text` part with content
  closes a run; `reasoning`, empty `text` and `step-start` close nothing (the
  overview, the batch-1 card, the conformance suite and the frozen client
  module all say so, and the same three-part shape from the log is the frozen
  case). And the runtime stops writing such parts at all: PROTOCOL 1.4.1
  section 6 states that a text or reasoning part that would stay empty is
  never written, implemented as `EmptyPartGate` in the chat event writer,
  which holds a start until its first delta and drops the pair when the end
  comes first. The thread also renders nothing for a settled reasoning part
  with no text, so the eight empty disclosures that stood above the rows are
  gone with the rows' splitting. The recorded acceptance turn never had an
  empty part, which is why fifty frozen tests and two live journeys passed
  over a shape the real model produces on every step.

  The same turn showed two more things the recorded turn had hidden. The
  trace read `Working...` while the assistant was in fact waiting on the
  user's answer to a consult question: the summary now derives from the rows,
  `Working...` only while a call runs, `Waiting for you` while none runs and
  one waits on an approval or an answer, `N steps` once settled; the frozen
  calm-default module and the frozen e2e journey pin the new word. And the
  first thing a reader saw was `Title set: ...` drawn as a figure with a rule
  and 24 px margins, for a title the sidebar already shows; the
  `data-conversation-title` part now draws nothing in the thread.

* **The e2e lane's blanket 401, a cross-tier settings leak, two tools that
  could not be addressed by strategy id, and a gate that stopped at the spec
  files.** A Playwright worker signs in through the dev-login route as
  `worker-N` and carries the one shared registered VEuPathDB test token, so
  `require_session_matches_wdk_identity` answered 401 `WDK_IDENTITY_MISMATCH`
  on every WDK-backed route. The identity match belongs to a session minted
  from a VEuPathDB identity; a dev-login session is a synthetic user with no
  such account. The dev-login route marks its JWT, `decode_session_token`
  reads the mark, and the `Principal` carries `credential="dev-login"` beside
  `veupathdb-bearer`, which the match returns early for. The login refusal is
  unchanged, so a dev-login session still needs a registered non-guest token.
  Production cannot mint the credential and a test says so twice: the app
  built without the mock overlay carries no dev-login route, and the dev
  router is the only caller of `create_dev_login_token`.

  `test_catalog_index.py`'s sync assertion answered `0 == 3` whenever the unit
  tier was collected in the same process, because `tests/unit/conftest.py`
  wrote `EMBEDDING_INDEX_SYNC_ENABLED=false` into `os.environ` at import and
  never restored it. The unit tier has no database and refuses network calls,
  so the write guarded nothing the tier did not already guard; it is deleted,
  the whole unit tier is green without it, the catalog test now pins the
  setting it asserts on the way its disabled twin already did, and an AST
  scan fails any tier conftest that writes the process environment again.

  `rename_strategy` and `clear_strategy` called `session.get_graph` directly,
  so they alone refused the VEuPathDB strategy id every other tool accepts;
  both now go through `_validation_helpers.get_graph` and say which ids they
  take when the lookup misses. And `check-no-first-nth` read only `*.spec.ts`,
  so a page object hid the escapes from every spec that called it: it now
  reads `e2e/pages/**` too, skips a call named in a comment, and reports zero
  after the four page objects were rewritten to name what they address.

* **The Lead can throw a strategy away, and only the Lead can.** `build_strategy`
  refuses a thread that already has a strategy and `edit_strategy` only changes
  one, so "scrap this and start again" had no tool behind it: `clear_strategy`
  was registered in the execution toolset alone, which the Lead reaches only
  through `recover_failed_steps`. It is now a Lead tool - a thin
  `clear_strategy(ctx: RunContext[LeadDeps], *, confirm: bool)` that builds
  `AgentDeps` through `agent_deps_for` and delegates to the standalone tool -
  registered `requires_approval=True`, so the user answers a card before a step
  is removed. Its card reads "Clear the strategy? This removes every step from
  this thread and from VEuPathDB." through a new `approvalPromptFor` seam in
  `lib/utils/toolNames.ts`; `ApprovalCard` now renders the whole sentence its
  caller wrote instead of appending one, and every other tool keeps the
  standing "X needs your approval before it runs." The build refusal and the
  Lead's instructions name the tool again. The execution toolset's registration
  is gone with it: a repair sub-agent has no business deleting the strategy it
  was sent to repair, and two registrations would be two approval surfaces for
  one act.

* **`get_live_strategy_state` asks the site for every count.** After a hand edit
  in the graph editor the tool answered from `sync_state.step_counts`, which the
  editor never writes: the root read 15 for a strategy the editor showed
  returning 7, the edited step read null, and the step's name still said "top
  20%" while its parameter said 90. `read_live_state` is now async, takes a
  the site id, and sources every count from `read_wdk_step_counts` - a
  count the site does not answer for is reported as unknown, never as the count
  from the last build. Step parameters are serialized through `wire_map`, so the
  Lead reads `min_expression_percentile: "90"` rather than a nested value model,
  and the tool's description says the parameters outrank the step's name. The
  summary says "count not available" with `status="warn"` instead of "0 genes".
  Measured on the card's state: root 7, the edited step 752, the text step 2122.

* **One row-to-session parse, pinned by a test.** The assistant spec and the
  worker runtime each used to hold the same guard-parse-fallback over
  `conversation_strategies.strategy_ast`; both now call
  `services/strategies/session_factory.py::persisted_graph`, which raises
  `StrategyAstCorruptError` (`STRATEGY_AST_CORRUPT`) rather than swallowing a
  parse failure into an empty graph. Nothing asserted the two agreed, so
  `test_row_to_session_is_parsed_once.py` now serves one row to both callers and
  checks the graphs, the step counts and the WDK step ids match, that a corrupt
  row stops each of them by name, and that both modules read the one function.

* **The thread's trim now mirrors both tails pydantic-ai refuses.**
  `settled_history` popped trailing messages until the last one was a
  `ModelResponse` with no tool calls, which kept a response the provider paused
  (`state == "suspended"`) as the thread's tail; `UserPromptNode` raises
  `UserError` on a new prompt over that tail as surely as it does over an
  unprocessed tool call. The trim now treats a suspended response as unsettled
  and drops it with its request. A response in state `incomplete` still
  settles, because the library accepts it.

* **A warm-up death now reaches `/health/ready`.** `_warm_up_subsystems` runs
  as a spawned task and each step catches its own expected exception tuples, so
  a type outside those tuples killed the task and left the remaining subsystems
  reporting "loading" forever, traced only by asyncio's
  exception-never-retrieved log at garbage collection. The spawn now carries a
  done callback that logs the exception and calls
  `ReadinessState.fail_loading`, which fails every subsystem and catalog that
  is neither ready nor already failed, with `<TypeName>: <message>` as the
  error. A step that already reported its own error keeps it.

* **The devtools summary counts every tool call its own log holds.**
  `RunCapture` built its call list from `data-sub-agent-step` chunks alone, so
  a turn that ran one agent printed `toolcalls=0` over an `events.jsonl` full of
  `tool-input-available`, and a Lead turn counted its sub-agents' inner calls
  but never its own dispatches. The count is now the union, deduped by
  `toolCallId`: every id a `tool-input-available` announces, plus every
  captured sub-agent step that reached a terminal state. A recorded site_help
  mock run (one `list_veupathdb_sites` call, `toolcalls=0` in its own
  `summary.json`) is pinned as a fixture under the devtools unit tests.

* **A sweep's variants now advance in lanes of their own (protocol 1.5.0).**
  Every variant of a parameter sweep emitted `data-task-progress` under the
  same `id` (the task id), so section 5.2's reconciliation left one part for
  the whole fan-out and the bar jumped between variants and moved backwards.
  `task_progress_event` takes a `lane` and emits `id=<task id>:<lane>`; a
  scoped emitter derives its lane from its scope's values and keeps a
  coalescing budget and an unwritten update of its own, so three variants of
  three updates leave six rows under three ids instead of four rows under one.
  PROTOCOL 6.1 states the lane rule, says the lane is read from `toolSpecific`
  and never parsed out of the `id`, and the client's conformance suite pins two
  lanes reducing to two parts. The thread card renders one row per lane,
  ordered by lane, and a task that runs one sequence is unchanged: bare task
  id, one row.

* **PROTOCOL 6.2 now states the resume sequence the runtime emits.** A resumed
  approval turn re-enters the parked `toolCallId` with `tool-input-available`
  and then `tool-output-available`, and never a second `tool-input-start`:
  pydantic-ai's resume emits its own input-available, which marks the id
  started, so the adapter's missing-start backfill never fires. The document
  described a start-first sequence, so a consumer written from the page alone
  built a reader the reference producer contradicts. Section 6.2 now says the
  resumed turn carries the input chunk alone and that a client MUST open a call
  on `tool-input-available` whether or not a start came before it. The producer
  is unchanged; the client's conformance suite gains the resume half of the
  approval arc.

* **The dead-code checker is pinned, wired, and has no whitelist.** `vulture`
  was configured in `apps/api/pyproject.toml` but declared in no dependency
  group, so `uv run vulture` resolved to a global `vulture 2.14` on a
  pre-3.14 interpreter and reported 69 valid PEP 758 / PEP 695 / `match` files
  as `invalid syntax`. It is now `vulture>=2.16` in the api dev group, where the
  same command reads every file and exits 0. Two gates run it, spelled
  identically: the `vulture-api` pre-commit hook and the `Check for dead code`
  step of the `Lint API` job. `vulture_whitelist.py` is deleted: all 49 entries
  named functions, `min_confidence` is 80, vulture scores an unused function at
  60, and the run without the file returns the same findings as the run with it
  - 16 of the 49 names had no `def` left in the tree. Its live replacement is
  `ignore_names = ["CursorResult"]`, for six imports whose only use is inside
  `cast("CursorResult[object]", ...)`, which ruff `TC006` requires to be a
  string and vulture does not resolve. The one true finding is fixed:
  `Settings.model_post_init` took `__context`, an unused parameter under the
  old positional-only spelling, now `_context: object, /` to match
  `BaseModel.model_post_init`. `min_confidence` 60 was measured and rejected at
  997 findings.

## 2026-08-29

* **Thread redesign batch 3 is closed, and with it the plan: every color is
  a token and every token has both grounds.** `globals.css` now holds one
  light palette on `:root` (neutrals moved onto a single 210 to 215 hue
  family, the status trio untouched, a new chart series that clears 3:1 on
  white) and one dark palette under `:root[data-theme="dark"]`, the `dark`
  variant bound to that attribute so no operating-system setting can fire it,
  the `.dark` class gone, and every shadow, chart, step-kind and scrim token
  defined twice. `chartTheme` reads the ground it is on, `applySiteTheme`
  computes a legible brand primary and its own foreground for either ground,
  the WCAG math exists once in `lib/color/contrast.ts` with a dark gate beside
  the light one, and 110 palette-shade utilities across seven consumer
  clusters became token classes or runtime token reads with value-asserting
  tests. Dark `--destructive` moved from the plan's 65 to 73 percent lightness
  because its own tint measured 3.80:1; the plan's dark kind soft and ring
  literals became `hsl(var(--kind-X) / a)` references because the frozen theme
  module reads `rgb()` as a color and `hsl()` as not. The verifier's first
  pass failed on an undeleted backlog card, a `dark:bg-destructive/60` twin
  that measured 3.55:1 under the new dark foreground, and a validation
  definition an external palette script disputes; the card now states which
  criteria "validated" means. Sixteen dead keyframes, utilities and classes
  left the stylesheet with a referrer proof for each survivor. Both frozen
  journeys pass on the e2e stack; the chart-token backlog item and the
  initiative card are deleted.

* **Thread redesign batch 2 is closed: the thread reads as prose with a quiet
  trace under it.** A turn now renders through `TraceAnchor`, which runs
  `buildTrace` over the whole message and draws the trace once, at the run's
  first row-bearing part: one line per tool call (glyph, verb, the tool's own
  summary), sub-agent phases as labelled groups with their usage, the trace
  open while the turn runs and folded to `7 steps` once it settles. Durable
  jobs are task rows, the approval card is the one bordered box left, the
  fourteen science parts are flat figures with numeric captions (`6 of 12
  Sample, 34,320 of 68,640 pfal3D7 htseq counts`, `1,543 of 5,511 genes
  retained`), and raw JSON exists only under `showRawToolCalls`. Deleted:
  `SubAgentCallCard`, `ToolThink`, `DataTaskProgress`, `DataTaskCompleted`,
  `subAgentStep.ts`, and `Tool`/`ToolHeader`/`ToolContent` from the vendored
  primitives. The verifier's first pass failed on four things: an alpha-faded
  muted class the batch doc itself prescribed and the repo's status-token
  gate forbids; `turn-trace-summary` outside `turn-trace`, which the frozen
  e2e journey scopes inside it; the EDA study title outside
  `data-eda-analysis-state`, which the frozen EDA journey asserts inside; and
  weak assertions in four changed test files. Each became a lead ruling on the
  batch card and a fix; the second pass was green on every gate, both frozen
  Playwright journeys on the e2e stack, and five killed mutation probes, with
  one em dash left for the lead to strip. Batch 3 (tokens) is next.

* **Thread redesign batch 1 is closed: every tool call now says what it did.**
  The wire carries one additive data part, `data-tool-summary` (PROTOCOL
  1.4.0, sections 5.2, 6.3, 9, 12.2), and both conforming reducers fold it
  onto the tool part it names and append nothing. The client gained
  `buildTrace`, the one place the trace grouping rule lives, and
  `mergeSubAgentSteps` moved into it from the app. On the runtime side the
  helper is `assistant_core.graph.tool_summary` (`with_summary`,
  `truncate_summary`, `count_noun`): it lives in the runtime because the
  pilot's boundary test forbids `site_help` from importing `pathfinder.ai`,
  and because nothing in it names a gene. Eighty-three registered tools plus
  `site_help`'s two return through it; the four durable tools emit their line
  at resume; an inner sub-agent call's line becomes the step row's text and
  never reaches the main stream; one call id carries one phase name and one
  sub-agent role. The verifier's first pass failed on three things the
  implementers' own suites could not see: two `empty` statuses (`0 of 4,279
  Gene Phenotype Data`, `0 steps, 0 genes`) that no test drove, and a golden
  SSE gate that did not admit the kind. Fixed with value-asserting tests that
  now kill those probes. Sixty-two redundant `truncate_summary` wrappers came
  off the call sites because the helper normalises once; the five Lead
  dispatch tools emit no summary because their native chunks never reach the
  wire and the sub-agent card already carries the line. A live worker turn
  after the rebuild shows the summaries on the log with every id resolvable.
  Process ruling from this batch: implementers run only their own tests; every
  full ladder, integration run, rebuild and live proof belongs to the verifier.

* **Thread redesign batch 0 is frozen: the tests exist before the code.**
  `docs/knowledge/thread/plan/` records the decision to replace the thread's
  stacked cards and raw tool JSON with a calm science-first default: one
  column of prose, tool activity as a quiet trace of one-line summaries, typed
  science parts as flat figures, durable jobs as task rows, an approval card
  only when the user must act, and the two existing settings flags as the
  whole dev mode. The plan was drafted, then verified line by line against the
  code (about forty citation corrections) and eight lead rulings settled the
  wire (`data-tool-summary` rides its own data chunk because the AI SDK's live
  reducer rejects extra keys on tool chunks; a summary may precede or follow
  its call's output; inner sub-agent summaries are lifted onto the step; one
  entity-count caption format; ASCII usage separator; one phase-label set;
  notices and task rows are never figures). The frozen layer: a recorded
  42-chunk turn built from real EDA fixtures, 22 frontend tests for the calm
  default, the dev mode and the figures, 20 client conformance cases for the
  summary reduction and `buildTrace` (one non-empty run, seven rows, three
  figures, `Working...` while a call awaits approval), an e2e journey gated on
  `THREAD_ACCEPTANCE=1`, and a theme completeness test that skips until the
  dark block exists. All fifty skip cleanly today; the EDA suites are the
  regression net and stay at 41.

* **Embeddings became an API call and two Postgres tables.** The local
  `nomic-embed-text-v1.5` is deleted: 547 MB on disk, 967 MB resident per
  process before it encoded a text, one sequence at a time on CPU in the api,
  the worker and `wdk-mcp`. Measured before the change on 2026-08-29: a cold
  rebuild of every cache was about 110 minutes, the portal alone about 50;
  thirteen of the fourteen committed `.npz` files carried the retired shape, so
  7,184 of 7,699 shipped rows were dead; the quadlets persisted no cache volume;
  and `search_example_plans` re-embedded the whole public strategy list on every
  call, 46 s for a patient client. Every vector now comes from OpenAI
  `text-embedding-3-large` at 1024 dimensions through
  `assistant_core/embeddings/openai_embedder.py`, cut at 2000 characters,
  grouped into requests of at most 256 inputs and 200,000 characters, and run
  eight at a time in input order.
  `assistant_core/embeddings/record_manager.py` owns `embedding_vectors` and
  `embedding_index_entries`: a vector is addressed by
  `sha256(model + "\n" + text)`, two indexes sharing one text share one row,
  `sync_index` embeds only what changed and answers with a `SyncReport`, and
  `search_index` ranks in SQL with `1 - (embedding <=> :query)`. The three index
  ids are `catalog:{site_id}`, `eda-studies` and `public-strategies:{site_id}`.
  Two of the three old indexes multiplied unnormalized vectors, so their scores
  ran to about 340 and the catalog multiplied that by `_SEMANTIC_BOOST = 15.0`:
  the ranking was embedding order and the lexical score did not participate.
  Measured on the plasmodb snapshot over its 515 searches, the top lexical
  score of five research queries was 45.3, 106.9, 44.7, 49.2 and 60.4, so the
  boost is 70.0 against a cosine and a cosine of 0.7 buys 49.0, the median top.
  `EMBEDDING_INDEX_SYNC_ENABLED` replaces `EDA_STUDY_INDEX_BUILD_ENABLED` and is
  true only on the api; the worker and `wdk-mcp` search what the api wrote, in
  compose and in both quadlets, which one test now reads for every guarded unit. An
  `EmbeddingUnavailableError` never 500s: the catalog ranks lexically, the study
  search matches names and says so, the public strategies fall back to token
  overlap, and memory retrieval returns nothing. The nomic query and document
  prefixes are gone with the model, and with them the LangGraph
  `aembed_documents` trap. Recorded as [embeddings are an API call and a
  Postgres record manager](decisions/embeddings-are-an-api-and-a-record-manager.md).

* **A study description is bounded, and a dead worker no longer holds a turn
  open.** One prompt on plasmodb called `search_eda_studies`, the worker built
  the EDA study index cold, and docker reported `oom` and `die 137` on
  `pathfinder-worker-1` 49 seconds later. Measured in the api container with a
  real login: 759 studies, `study_enriched_text` up to 24,820 characters, a
  cold encode of 458.7 s peaking at 4.70 GiB. `study_index.DESCRIPTION_LIMIT`
  now cuts the description at 2,000 characters, which touches 34 of the 759
  and brings the same encode to 368.4 s peaking at 1.19 GiB. Batching the
  model was measured and rejected: a length-sorted batch under a 16,384
  padded-character budget was OOM-killed inside the worker after 47 seconds,
  so `_embed` keeps `batch_size=1` and one document is the only thing in the
  arena. The EDA service answers with the portal's catalog, byte-identical on
  plasmodb, toxodb, hostdb, vectorbase and orthomcl, so the rows live in one
  content-addressed store, `eda-studies.npz`, and `preload_study_indexes` in
  the api warm-up fills it under the service account token, leaving the worker
  nothing to encode. The worker is also forbidden to encode it:
  `EDA_STUDY_INDEX_BUILD_ENABLED=false` sits beside `CATALOG_REFRESH_ENABLED`
  on that container, and a store that does not cover every study raises
  `EdaStudyIndexNotReadyError`, which `search_eda_studies` returns as guidance
  rather than starting a second encode beside the api's; concurrent encodes
  measured 1.170 s per text against 0.485 s alone. On the release side,
  `release_stalled_jobs` now also asks
  procrastinate for the jobs of a worker whose `last_heartbeat` is older than
  the new `worker_dead_heartbeat_seconds` (300 s, ge 60), so a killed worker
  loses its lock five to six minutes after it dies instead of at the hour-wide
  started-age timeout, and Stop calls the same release directly. The window is
  300 s and not 60 s because a live worker was measured 153 s behind its own
  heartbeat during a long frame, so the heartbeat starvation is the
  prerequisite for lowering it; the 30 s window in `platform/health.py` is a
  different question and keeps its number. A released
  turn, and a turn whose own driver raises, now write one `tool-output-error`
  per tool call they left open before the terminator; `PROTOCOL.md` 1.3.1
  states the rule and the client's conformance capture carries it.

* **EDA reached both surfaces, and the seven-batch plan is closed.** A
  researcher can open an EDA study from the thread and from a workbench-style
  tab, and the two edit one analysis: `services/eda/authoring.py` is the only
  writer, every mutation answers with the same `EdaAnalysisState`, and
  `data-eda.analysis-state`, `data-eda.subset-preview` and `data-eda.viz`
  carry it to chat while `GET|PATCH /api/v1/conversations/{id}/eda` carries
  it to the tab. Batch 7 grew the three chat renderers into real cards (the
  volcano and scatter on a canvas beside their readouts, chips from the
  backend's `filterSummaries`, every count against its unfiltered total, an
  "Open in EDA tab" affordance), added the right-rail EDA panel that marks
  unseen EDA activity, and proved the loop with three Playwright journeys
  (chat-only render, tab edit returning on the next state part, export to a
  step the strategy rail lists) plus a conformance spec that parses every
  e2e fixture through the generated schemas, the last of which caught a
  fixture point that omitted its nullable p-values on both the feature spec
  and the frozen journey. The verifier failed the first pass on a chip keyed
  by its text, an untested rail marker and an untested scatter guard; all
  three were pinned and re-probed. The frozen acceptance layer closed
  56 backend, 41 frontend and 3 journey tests without a single line changed
  by an implementer; the lead's edits to it were four constructor
  completions and the journey fixtures' wire shapes. Three repo-wide gates
  stay red on files outside the plan and are backlogged: weak assertions
  (99), Playwright index locators (16), and the dev server's Turbopack flag.
  The concept and architecture-fit documents now read as built, every batch
  document is accepted, and `execute-eda-integration-plan.md` left the
  backlog.

## 2026-08-27

* **A strategy with no spec now describes itself, and a "preserved" claim is
  computed.** Batches E1 to E3 of
  [the edit_strategy fix plan](../design/2026-08-27-edit-strategy-fix-plan.md)
  landed. `domain/strategy/spec_hydration.py::spec_from_ast` reconstructs an
  `OperationalSpec` from the persisted `StrategyAst` - one criterion per
  non-combine node, keyed on the step id, holding the node's bound parameters
  verbatim - and the pre-turn hook runs it whenever the checkpoint holds no
  spec and the session holds a strategy. Measured on the thread the plan
  names: its checkpoint carried `operational_spec = None` on entry and its row
  carried 15 nodes with 15 WDK step ids, so the run that asked the user to
  re-type their filters was mechanism (a), and E1 is the batch that closes it.
  FRAME can no longer report `spec_ready` over a draft with no bound criterion,
  and its workspace prints every bound value in wire form instead of a
  60-character label. `domain/strategy/spec_diff.py::diff_specs` compares the
  spec a turn started from against the one it produced; an undeclared drop and
  a "kept" criterion whose values moved are both a `ModelRetry`, and the ledger
  renders `kept N, changed N, added N, dropped N` from the same comparison.
  Recorded as [preserved is computed, never
  written](decisions/preserved-is-computed-never-written.md). The `E6`
  checkpoint flush is owed: `StrategyDomainState` gained `spec_before_turn`.

## 2026-08-28

* **The EDA tab is no longer a dead end, and one route builder owns the canvas
  path.** A binding read that answers 422 over an out-of-vocabulary stored
  filter now offers "Open a different study" beside Retry; it sends
  `{action: "unbind"}`, clears the cached binding and the store, and shows the
  picker, with the server's detail quoted verbatim. `lib/routes.ts` gained
  `strategyStepUrl` beside `strategyCanvasUrl`, and the six hand-built paths
  call them - one of the six carried no site id, so it pointed at a route that
  does not exist. The entity tree now skips a variable whose `hideFrom` names
  `everywhere` or `variableTree`, while a filter already in force on such a
  variable keeps its chip and can still be removed. The same sweep then closed
  the chat path: eleven thread literals now call `chatUrl`, eight root literals
  call `chatRoot`, four site-less entry points redirect through the new
  `PORTAL_SITE_ID`, and a grep for a hand-built conversation path outside
  `lib/routes.ts` returns nothing.

* **A completed EDA compute puts a volcano on the thread, and the study
  detail carries the site's display advice.** `run_eda_compute_impl` reads
  `volcano_view` at the default cut and emits `data-eda.viz` through the same
  writer, right after the analysis-state chunk that names the revision the
  plot belongs to, so `eda_viz_chunk` has a production caller and the chat
  card draws a real plot. `volcano_view` now keeps a row whose effect size
  reads and whose p-value does not: it has an x coordinate, so it is drawn,
  never retained, and carries a null `pValue` that both surfaces count; only a
  row with no readable effect size is dropped. On the recorded compute that is
  201 points tested, 67 retained and 201 placed, one of them with no p-value.
  `EdaVariableResponse` and `EdaVariableOut` now carry `hideFrom`, read from
  the upstream variable in `variable_out`, so the tab can hide what the site
  hides while the chat tools keep every variable filterable.

* **EDA batch 6 is closed: the tab exists.** `/{siteId}/conversation/{id}/eda`
  mounts `features/eda/EdaWorkbench` behind the same `ChatShell` yield the
  strategy canvas uses. A `StudyPicker` searches and binds; a bound analysis
  mounts three cells keyed by `analysisId` so a switch remounts them: the
  `SubsetCell` (entity tree built from the flat detail, one `/count` per
  entity, filter editor dispatching on the server's `filterType`, chips from
  the store's parsed filters, unparsed filters reported, bar or histogram
  sparkline by `dataShape` with a coverage line), the `ComputeCell`
  (differential expression config built from live metadata with `DESeq` or
  `limma` on the wire, submit-or-poll by the byte-identical `run-compute`
  body, seven job states named), and the `VizCell` (volcano thresholded
  client side with a test proving zero `/viz` calls on a threshold change,
  the selected-gene readout beside every chart, scatter from the same
  cloud, the other charts named unavailable, refetch keyed on the completed
  job). `ExportStepButton` gates on `canExportRows` and a complete job and
  presents two success states with exact copy: the export began the
  strategy, or it added a draft root that is not pushed, decided
  structurally from the returned strategy and linked through the new
  `strategyCanvasUrl`. Before the batch, three reconciliations landed so it
  coded against the wire and not a sketch: every EDA response field became
  required (above), an export on a thread with no strategy now begins it
  through the one `persisted_graph` loader that replaced three divergent
  copies (the strict one in `strategy_ops` was the 404), with the op
  algebra's `ApplyError` rendered as 422 where it was an unhandled 500, and
  the frozen e2e journey's fixtures were corrected to the generated shapes.
  The verifier failed the first pass on evidence: local cell state outlived
  an analysis switch (measured "Sample6 of 12" after the switch), a second
  compute never refreshed the volcano (0 `/viz` calls), a Retry was missing,
  six named states had no test, and three probes survived; every item was
  fixed and re-probed, 18 of 18 killed on the second pass. Lead rulings
  recorded as backlog: the tab must honor `hideFrom` once the route carries
  it; the read path's refusal of an out-of-vocabulary filter needs a way out
  of the error state; no production path emits `data-eda.viz`, which batch 7
  owns. Ladders: unit 3223, integration 644 with 78 skipped, acceptance 56
  of 56 and 31 of 31, frontend 2512 vitest with the EDA tree at 187, three
  Python packages format-clean, `batch67-parts` red as designed.

* **Every EDA response field is required, and the analysis state counts its
  own entities.** The defaults are gone from the five parts in
  `shared_py.stream_parts.eda` and from every response model in
  `transport/http/schemas/eda.py`; a field that can legitimately be absent is
  required-and-nullable (`revision`, `pValue`, `adjustedPValue`, `job`,
  `step`, the gene-entity keys), and the request models keep the inputs a
  client may omit. `openapi.json` lists all thirteen `EdaAnalysisState` keys,
  the generated types and zod schemas carry no optional marker, and the store
  and the three card renderers read the fields with no `??`.
  `services/eda/authoring.py::subset_entity_counts` walks the study in tree
  order and fills `entityCounts`, which the only producer left empty; the
  whole size of an entity is cached beside its study detail
  (`catalog.py::unfiltered_entity_count`), so a mutation costs one count per
  entity and not two. `analysis_state` became async to own that read, so the
  subset predicates now run on the read path as well: an analysis edited
  elsewhere into an out-of-vocabulary value is refused by name rather than
  reported as a subset of zero, which is what upstream would answer. This
  closes the backlog item the batch-5 verifier raised.

* **EDA batch 5 is closed: the charts and the store exist, and the wire
  feeds both.** `lib/components/charts` is one ECharts 6.1.0 registry
  (`echartsRegistry.ts` holds the only value imports; everything else is
  `import type`), a ref-callback `EChart` wrapper that inits once, re-applies
  options and disposes in its own teardown, and pure option builders for the
  volcano (three series plus threshold guides, null p-values dropped and
  counted), the histogram and bar (label union, zero fill, real overlay), and
  the scatter (finite pairs only), each pinned to exact option arrays and
  tooltip strings. `lib/eda/volcanoSelection.ts` is the one selection rule
  (effect inclusive, significance strict, up before down) and the acceptance
  suite sweeps it with properties. `state/eda.ts` is `useEdaStore`, whose
  `supersedes()` is the overview's reconcile rule verbatim (analysis switch
  wins and clears, null revision on either side takes the last write, `>=`
  accepts), filters parsed per entry with the generated `edaFilterSchema`
  and failures counted. `lib/api/eda.ts` wraps the six routes and the GET
  through `requestJson` with generated schemas only; the three batch-4
  renderers hydrate the store in render with no effect. Two reconciliations
  landed inside the batch: `GET /conversations/{id}/eda` now carries the same
  `analysis: EdaAnalysisState | null` the part and the PATCH carry, built by
  one `read_analysis_state` that does not bump the revision (its seven flat
  fields deleted, `descriptor` made required-nullable), and the regenerated
  `conversationEdaResponseSchema` was adopted by the transport tests in the
  same window. The verifier ran twenty mutation probes and killed twenty,
  accepted eight implementer deviations on evidence (a namespace import of
  `echarts/core` because a named `use` trips the hooks lint; generated
  names over the card's), and left three notes the lead resolved: the
  palette backlog understated `--chart-3` (it fails the band, the entry now
  says so), the transport acceptance and the card spelled the compute
  payload `{appName, config}` where the wire says `{type, configuration}`
  (both corrected, the lead's one acceptance edit this batch), and the
  generated `EdaAnalysisState` marks nine always-filled fields optional
  because the Python model defaults them, which is now a backlog decision
  and a batch-6 wire truth (read the analysis through the store, never with
  `??` off a payload). Ladders: unit 3193, integration 640 with 78 skipped,
  acceptance 56 of 56, frontend 2340 vitest with batch-5 store, selection
  and transport at 31 of 31 and `batch67-parts` red as designed, four frozen
  trees byte-identical to the baseline.

* **EDA batch 4 is closed: the tab has its API and its types.**
  `transport/http/routers/eda.py` serves the seven pinned operations under
  the real `require_registered_wdk_identity` gate: study search and detail
  (one `describe_study` builder shared with the chat tool), count and
  distribution refusing an out-of-vocabulary value with 422 before any wire
  call, the thresholded volcano view, and `GET|PATCH
  /conversations/{id}/eda` with a five-way `action` union whose handlers
  call the same service bodies the agent tools call (`bind_analysis`,
  `apply_filters`, `submit_compute`, `export_analysis_step` were extracted
  into `services/eda/` so the tab and the tools cannot drift), every
  mutation bumping the thread's revision, and a `{analysis, job, step}`
  envelope with `analysis` required-and-nullable. On the TypeScript side
  one `yarn generate:types` carries the three `data-eda.*` part payloads,
  the six route schemas and, after `EdaFilter` became a PEP 695 `type`
  alias so Pydantic names it, the seven-variant `edaFilterSchema` the
  frozen store suite imports; the three text-only renderers keep the
  data-part map total. Ring 2 rejected once on evidence, and it was the
  batch's most important catch: the router shipped with a weaker
  session-presence gate because the implementer's test fixtures had not
  requested the harness's identity override that every other WDK-backed
  route test uses, so production was widened to fit a fixture omission on
  a security boundary; the verifier proved the real gate passes 10/10 and
  32/32 under the override, the gate was restored, the session gate and
  its tables deleted, and the decision doc's inaccurate paragraph
  reverted. The lead's one acceptance edit for the batch was that same
  fixture on the frozen suite. Two semantics the verifier traced are
  recorded for batch 6 rather than hidden: an export beside an existing
  strategy is a detached, never-pushed second root, and an export on a
  thread with no strategy is a 404. Ladders: unit 3191, http+eda
  integration 251, acceptance 56 of 56 (batch 4 at 10/10 under the real
  gate), frontend 2229 vitest with the acceptance config still all-skipped,
  the protocol package unchanged across three regenerations.

* **EDA batch 3 is closed: the conversational seam works end to end.** A
  researcher's thread can now search studies, open an analysis, set filters
  through a validated sheet, preview the subset, run differential expression
  as a durable background compute, and export the result as an ordinary
  step. The pieces: three `data-eda.*` stream parts in `shared_py` composed
  into the product's registration beside the strategy parts; seven Lead
  tools (`ai/tools/standalone/eda_*.py`, `ai/tools/toolsets/eda.py`) with
  `set_eda_filters` copying the `set_criterion` sheet pattern and every
  mutation bumping a per-thread revision counter on the new
  `conversation_analyses` row (migration `2026_08_28_0002`); the
  `services/eda/binding.py` hub; `create_eda_step` bridging into
  `apply_operations_and_commit` with the spec serialized once through
  `services/eda/export.py`; and `run_eda_compute` as a `@durable_tool`
  whose worker impl (`jobs/impls/eda_compute_impl.py`) drives the compute
  to `complete` before any step exists, so the WDK bridge's HTTP 202 is
  never surfaced. `durable_tool` was generalized to a two-member
  `DurableIdentity` Protocol so the Lead can call it. The proof is Verifier
  2's in-tree scripted conversation (`tests/integration/eda/test_eda_conversation.py`)
  through the real chat endpoint, worker, graph and event writer, asserting
  persisted chunk kinds and values (revisions 1 then 2, counts 4011 of 4279,
  a graph snapshot with a `GenesByEdaSubset` node), plus a live lane that
  pushed WDK strategy 330555673 whose EDA-backed step counted 5556 genes.
  Ring 2 rejected on evidence six times and each was closed by a named
  test: an unpinned longitude filter type, a vacuous hideFrom test whose
  fixture held no hidden variable, a non-atomic-increment mutant that
  returned 1 for all 20 concurrent calls, a significance-only threshold
  that escaped as a raw ValueError, a card-prescribed `import as`, and a
  duplicate view model. One verifier premise was refuted by the implementer
  with evidence (pydantic-ai dumps tool returns by alias, so the camelCase
  docstrings were right) and turned into a guard test. Docker crashed
  mid-batch from host-disk exhaustion (36 GB pruned; the killed implementer
  was resumed from an inventory of its tree). Recorded for later: the
  pre-existing resume-replay duplicate now measurably double-applies an EDA
  compute; the generic and per-dataset subset searches counted 5556 against
  5602 for one filter; the chat SSE test helper splits on U+2028. Full
  ladders green: unit 3177, serialized integration 594 passed 78 skipped,
  acceptance 46 of 47 (batch 4 pending), runtime package 354 with zero EDA
  names.

* **The plasmodb live lanes from EDA batches 1 and 2 have now run.**
  plasmodb.org returned after a day-long outage on their side, and every
  deferred live assertion passed on the first credentialed run: the client
  lane against the recorded catalog and counts (4011 of 4279), the compute
  lane reproducing the measured 5511 rows to 1543 retained (529 up, 1014
  down) at 1.0/0.05, and the search census (68 spec-carrying searches, 13
  named Eda, exactly 1 inert). One drift check failed for a true reason and
  was narrowed: a `user_submitted` study the veupathdb.org portal lists is
  invisible on plasmodb.org, because user uploads are visible per project
  and per account, so the recorded-is-a-subset-of-live assertion now
  compares curated studies only. Both batches' open items are closed.

* **EDA batch 2 is closed: the services exist.** `services/eda/catalog.py`
  resolves a dataset to its study through `/permissions` only (never derived
  from the id) and caches each study's detail under `study_cache_key`, the
  content hash for a curated study and `lastModified` for a user study, so
  a reloaded study re-fetches; `integrations/embeddings/study_index.py`
  ranks studies with the same fastembed index the WDK catalog uses, its
  three cache helpers now shared rather than copied, and never resolves.
  `services/eda/authoring.py` owns the analysis document: `serialize_spec`
  is the one `model_dump_json` site (an empty analysis serializes to the
  empty string, never `{}`; a frozen allowlist test fails on any second
  dump across six source trees), `EdaStepRequest` refuses a spec whose
  `studyId` differs from `eda_dataset_id` (both dataset ids), and
  `verified_count`/`apply_filters` run the domain predicates before any
  wire call because upstream answers an out-of-vocabulary value with 200
  and count 0. `services/eda/compute.py` submits with the STUDY id, polls
  the six-state job, and `retained_summary` applies the WDK bridge's exact
  volcano rule (a verifier replayed the recorded statistics by hand: 67
  retained of 201, 33 up and 34 down). `services/catalog/eda_backed.py`
  detects an EDA-backed search by parameter presence, never by name, and
  guards the `EDAUD_` upload sentinel so an empty-state vocabulary term is
  never offered as a choice. The frozen batch-2 acceptance module passes
  19/19 unmodified. The lead made its one allowed acceptance edit: the
  suite and the plan had constructed `WDKVocabTerm` with keyword arguments,
  but the model is the WDK wire triple, and an implementer's attempt to
  widen the production model to fit the test was rejected and reverted.
  Two verifier FAILs were closed on evidence (a sentinel word boundary and
  a guidance wiring path each survived a mutation until a test was added),
  a root fix typed `WDKSearch.dynamic_attributes` as `list[WDKAttributeField]`
  in place of a pre-existing `hasattr` probe, and the catalog integration
  file went from 47.75 s to 8.9 s by sharing one embedding cache across its
  tests. Open, not blocking: the live 5511-to-1543 assertion and the live
  search census have still not run because plasmodb.org is unreachable.

* **EDA batch 1 is closed: the integration foundation exists.**
  `integrations/eda/` now holds the hand-written Pydantic mirror of the EDA
  wire (`models.py`: the six-member variable union, the seven-member filter
  union that refuses `stringPrefixSet`, the analysis document with
  `derivedVariables` as ids, the six-state job, volcano rows that tolerate a
  missing p-value), eleven live-recorded fixtures with a value-pinning
  validation sweep, the typed httpx client (`client.py`, `analyses.py`,
  `errors.py`, `factory.py`; Accept exactly `application/json`, the STUDY id
  on computes, 400/403/422/500 mapped to typed errors, a missing registered
  token refused before the wire) hanging off `SiteInfo.eda_base_url`
  (`{site_origin}/eda`, no new setting), and `domain/eda.py`, the pure
  predicates over structural Protocols (filters against a study tree, the
  one-`VEUPATHDB_GENE_ID` rule, the differential-expression config) with an
  A-to-C cross-check proving the wire models satisfy them under pyright.
  Three Opus implementers, two Fable verifiers, then the lead. The protocol
  earned its keep on the first batch: Verifier 2 failed the predicates on
  evidence (two surviving mutations, six `match` arms statically dead to
  pyright because payload Protocols did not extend the base, an untested
  longitude epsilon) and the reopen surfaced a real behavior gap, a
  `category` variable accepted as a comparator; Verifier 1's twelve probes
  all died bar one killed only by the frozen acceptance suite, which is the
  suite doing its job. Open, not blocking: the credentialed plasmodb live
  lane has never run because plasmodb.org has been unreachable all day (its
  four pinned values were confirmed against veupathdb.org, the same
  deployment); re-run it when the host returns.

* **An edit turn is a delta over the strategy that exists, and a rebuild over
  one is refused.** Batches E4 to E6 of
  [the edit_strategy fix plan](../design/2026-08-27-edit-strategy-fix-plan.md)
  landed, and `edit_strategy` stopped being a classification nothing reads.
  `domain/strategy/spec_to_operations.py::operations_for` turns the computed
  `SpecDiff` into `GraphOperation`s over the live graph and hands them to the
  commit pipeline that already existed, so an untouched step is not rewritten.
  A build now re-keys the spec on the step ids it minted, which is what lets a
  criterion address a step at all; a thread that never framed gets the same
  invariant from the hydration. `build_strategy` refuses a thread whose graph
  has steps.

  Measured on PlasmoDB, one turn at a time through the debugger with the LLM
  mocked and WDK real. Turn 1 built strategy 330555313: `GenesByText` on
  P. falciparum 3D7 as WDK step 440180863 (129), `GenesByTaxon` on the same
  organism as 440180873 (5720), the UNION as 440180883. Turn 2 asked to swap
  the taxon criterion to P. vivax P01 and keep the rest. After it, WDK reports
  the same three step ids, `440180863` still carrying
  `text_search_organism: ["Plasmodium falciparum 3D7"]` at 129, and `440180873`
  carrying `organism: ["Plasmodium vivax P01"]` at 6861. No step was created and
  none was deleted. The ledger's diff read `kept 1, changed 1, added 0,
  dropped 0`, and the reply's preservation sentence is written from it.

  The same run found the debugger coupling two unrelated things: `--mock` set
  the mock provider AND skipped the WDK login, so a mocked run could not push a
  step and the proof had nothing to preserve. Only the LLM is mocked now; the
  login runs whenever credentials are present.

  Recorded as [an edit is a delta, not a
  rebuild](decisions/an-edit-is-a-delta-not-a-rebuild.md) and [a criterion and
  its step are one address](decisions/a-criterion-and-its-step-are-one-address.md).
  [build_strategy is not
  revision-guarded](decisions/build-strategy-is-not-revision-guarded.md) is
  amended: the exposure it accepted is closed, because the tool it applied to
  no longer runs on a strategy that exists. The checkpoint flush E3 owed shipped
  as `2026_08_28_0001`.

  Three backlog items left: the edit turn that dropped a criterion and said the
  rest was preserved, the one that rebuilt every step and reverted a hand edit,
  and the hydrated spec that made a whole strategy rebuildable with new step
  ids. A fourth left by accident: a formatter run over `src/pathfinder/tests/`
  reformatted the three EDA acceptance files ladder P's format rung was red on,
  which is the fix that item prescribed but not on its own, as it asked. Three
  arrived: the Lead has no tool to throw a strategy away now that
  `build_strategy` refuses one, the eval corpus cannot express a two-turn edit
  case, and the file-size gate is red on six modules rather than the two the
  item named.

* **The EDA plan gained a frozen acceptance layer, and it is already written.**
  The plan overview defined the protocol: a
  behavior-only conformance suite written before any implementation by QA
  agents who implement nothing, pinning live-verified VALUES at stable
  boundaries, pending until each batch closes (backend: `eda_acceptance`
  marker deselected from the default `addopts` plus `importorskip`; frontend:
  `*.acceptance.ts` files outside the default vitest include with a dedicated
  config; e2e: an env-gated playwright project), under a no-edit rule -
  implementers never touch the acceptance paths, a wrong test escalates to
  the session lead - and a new universal exit criterion: a batch closes only
  when its acceptance module passes unmodified. Verifiers additionally run
  mutation probes: flip two or three behavior-bearing lines and confirm the
  implementer's tests die. The suites exist and are pending-clean today:
  56 backend tests across four batch modules
  (`apps/api/src/pathfinder/tests/acceptance/eda/`, 4 modules skipped
  cleanly, every default gate green) and 41 frontend tests plus 3 e2e
  journeys (`apps/web/src/acceptance/eda/`, `apps/web/e2e/acceptance/`,
  default vitest and playwright collect zero of them). The QA pass also
  hardened the batch documents: the repository gained its named `increment`
  method, the 401 mapping and `install_transport` became pinned interface,
  unbind became explicitly idempotent, the count-route seam contradiction
  was resolved onto `verified_count`, `analysis` in the PATCH envelope is
  required-and-nullable, the volcano `selected` ordering is up-then-down,
  and batch 7's e2e snippets now use the rail's real accessible names.

* **The EDA integration has a verified implementation plan.** The plan tree
  held an overview - the layering, the co-edited-SSOT
  design (one analysis per thread, agent tools and tab clicks patching the
  same upstream document, both surfaces re-rendering from
  `data-eda.analysis-state` snapshots with a per-binding revision counter),
  the pinned shared contract, and the three-ring verification protocol - plus
  seven batch documents with per-implementer TDD task cards (17 implementers,
  10 verifiers, lead-closed batches). Drafted by two agents, then reconciled
  by the lead: the `PATCH /conversations/{id}/eda` route became a five-action
  union (`bind`, `set-filters`, `run-compute` as idempotent submit-or-poll,
  `export-step`, `unbind`) whose handlers call the same service bodies the
  agent tools call; the part payloads were settled on batch 3's models and
  every frontend fixture realigned; `VolcanoThresholds` gained its one
  definition; the duplicate distribution response collapsed onto the part's
  shape; and a boxplot chart with no data source and no consumer left the
  contract. Decisions taken with the user: both seams in one plan, ECharts
  for the statistical charts (canvas for the 5.5k-point volcano; networks
  stay on ReactFlow), co-edited state over read-only viewing. Execution is
  the one backlog initiative, which left the backlog when batch 7 closed.

## 2026-08-27

* **The availability cluster is closed: what a process holds is bounded, the
  server binds before the warm-up finishes, and an abandoned MCP call stops
  with its caller.** Three measured defects had one shared cause. Twelve of the
  fourteen catalog snapshots the image ships were 84.8 days old, and nothing
  persisted a refreshed one: every process start restored fourteen stale
  snapshots, spawned fourteen background refreshes at once, and each refetched
  a site and re-encoded its index - which is where the worker's 5.26 GiB, the
  api's hour-plus cold start and the `wdk-mcp` kill on a stale-cache site all
  came from. `catalogs_cache` now mounts over `apps/api/src/data/catalogs` in
  all three services, beside the `embeddings_cache` volume that already held
  the encoded rows, so a refresh is paid once and not once per recreate; a
  process-wide semaphore admits one `_fetch_from_api` at a time and a
  `KeyedLock` one build per site, so the peak is one build and not fourteen;
  `CATALOG_REFRESH_ENABLED` is `false` on `worker` and on `wdk-mcp`, because a
  build of one site was measured at 2.977 GiB and neither 2 GiB container
  survives it, and a sweep inside `wdk-mcp` restores a fresh-snapshot site in
  0.3 s for about 10 MiB; and `DiscoveryService` holds its catalogs in a
  `cachetools.LRUCache` over
  `SITE_CATALOG_BUDGET_MB` accounted megabytes (512 by default), so the held
  set is bounded by policy rather than by a kill. The accounting is measured,
  not guessed: a 7.9 MB plasmodb snapshot restores in 0.4 s with nothing
  encoded and costs 27.6 to 29.9 MiB resident, so a catalog is charged
  `1 MiB + 4 * payload + index.nbytes`. The lifespan now spawns
  `_warm_up_subsystems` instead of awaiting it and the model loads inside it
  run on a thread, so uvicorn binds while the catalogs load behind it: measured
  against the 73 minutes the item recorded, a recreate bound 43 s after
  container start and all fourteen catalogs preloaded in 5 s with nothing
  encoded, and the api settled at 2.21 GiB against the 5.66 to 8.83 GiB read
  off the same container before. The container healthcheck is `/health`,
  because a compose dependent needs a server that answers and a catalog loads
  on demand. `/health/ready` still reports per-subsystem and per-site progress for
  the UI's startup gate. On the MCP side a stateless streamable-HTTP call runs
  in the session manager's own task group, so an abandoned call is cancelled by
  nothing and the tool has to ask: `rank_public_strategies_semantic` embeds 64
  strategies per call and scores each batch as it arrives, and
  `search_example_plans` passes an embedding function that refuses once
  `Request.is_disconnected()` is true, holding that site's lock for the whole
  call so a second caller queues. Measured against the served endpoint: three
  calls abandoned at a five second budget all stopped about seven seconds after
  their clients left, the container kept `RestartCount` 0 at 1.089 GiB, the
  next call answered 200, and a patient client got its ranking in 46.2 s.
  `_encode` in the semantic index batches the same way, and the model now takes
  one document per batch: fastembed pads a batch to its longest text, and
  encoding 64 toxodb descriptions cost 166.5 s and 886 MiB at `batch_size=8`
  against 128.9 s and 186 MiB at `batch_size=1`. The eight-site sweep the
  kernel killed on its third site now finishes at 1375.8 MiB. Family 5 of the
  admission record names `search_example_plans` as the slow tool with a five
  second budget and settles all four of its checks, so three entries leave
  `UNSETTLED_CHECKS`. Recorded as
  [per-site catalogs are evicted under a budget, and the warm-up does not block
  the bind](decisions/per-site-catalogs-are-evicted-and-the-warm-up-does-not-block-the-bind.md),
  which names what was rejected: one process holding every index and serving
  the rest over MCP, parallel per-site encoding, a rebuild inside a capped
  container, `/health/ready` as the container healthcheck, and a budget sized
  from process RSS. One finding did not fit the fix and is now its own item:
  thirteen of the fourteen shipped `.npz` caches carry the retired
  `embeddings`-plus-`hash` shape that `_load_cached_rows` skips, so 7184 of the
  7699 shipped catalog entries have no usable row and a fresh deployment
  encodes them all before readiness closes.

* **The EDA bundle grew from orientation to a full specification.** Four
  parallel research passes deepened EDA (`veupathdb-py: docs/knowledge/eda/`) from 4 documents to 13, every
  claim verified against commit-pinned upstream source or live calls on three
  deployments, then re-verified by a second pass. New:
  data model (`veupathdb-py: docs/knowledge/eda/data-model.md`) (66664 variables scanned; the single-entity
  GET is lossy; `isCategory` never on the wire),
  subsetting semantics (`veupathdb-py: docs/knowledge/eda/subsetting-and-tabular.md`) (cross-entity
  propagation proven in both directions and across sibling subtrees;
  root-vocab is not subset-sensitive; a 20-row preview tier),
  filter algebra (`veupathdb-py: docs/knowledge/eda/filters.md`) (all 7 deployed types with exact error
  classes; out-of-vocabulary values return 200 count 0),
  derived variables and merging (`veupathdb-py: docs/knowledge/eda/derived-variables-and-merging.md`)
  (12 plugins, 10 proven live; `relativeObservationMinTimeInterval` is dead
  upstream; `resultsAll` gates merge output with 403),
  computes and jobs (`veupathdb-py: docs/knowledge/eda/computes-and-jobs.md`) (job id is a client-derivable
  MD5 shared across users; a real DESeq run observed queued to complete),
  visualizations (`veupathdb-py: docs/knowledge/eda/visualizations.md`) (volcano thresholds are
  client-side, network thresholds server-side),
  notebook presets (`veupathdb-py: docs/knowledge/eda/notebook-presets.md`) (the compute bridge is
  volcano-only by construction; the delayed answer is HTTP 202
  WDK-DELAYED-RESULT and the WDK call auto-starts the job; WGCNA exports
  genes through plain SQL, not EDA),
  genomics and WDK relations (`veupathdb-py: docs/knowledge/eda/genomics-and-wdk-relations.md`) (four
  relations, not one; per-dataset searches derive from
  SHA-1(datasetName)[:10]; the EDAUD_ sentinel vocabulary term 400s), and
  [architecture fit](eda/pathfinder-architecture-fit.md) (layer placement,
  the durable-tool mapping named mechanism by mechanism, EDA as a second
  admitted MCP source, hand-written Pydantic mirrors with pinned wire
  samples). The four baseline documents were corrected where the deeper pass
  falsified them, most notably: `differentialexpression` takes
  identifier+value variables, not a collection; the per-dataset searches use
  `GenesByEdaSubsetGeneric`; user studies have an empty `sha1hash`.

* **A one-agent assistant reads the thread it is having.** `single_agent_graph`
  built every run from `state.user_prompt` alone and passed no history unless
  the turn answered an approval, so a site-help thread answered "Yes, please
  proceed." with "What would you like me to proceed with?". The turn state now
  carries the thread's own pydantic-ai messages as JSON, written from the run's
  result and trimmed to the last complete exchange, and the graph reads them
  back as the run's `message_history`
  (a one-agent turn runs over the thread's own messages (`assistant-platform: docs/knowledge/decisions/the-thread-carries-its-own-messages-across-turns.md`)).
  The trim is what keeps a parked approval out of the carried history:
  pydantic-ai refuses a new prompt over a history holding an unprocessed call,
  and the card keeps its own resume history regardless. Rebuilding the messages
  from the durable chunk log was rejected, because the wire carries chunks
  rather than the call-to-result pairing a provider needs; a runtime window or
  summarizer was rejected too, since no thread has yet measured too expensive
  and pydantic-ai already puts that bound on the agent. The runtime's scripted
  test model gained `current_turn`, so a script that asks what THIS turn did
  stops reading the turns before it.

## 2026-08-25

* **A regenerated turn no longer wedges its conversation, and a thread that
  cannot render no longer takes the page with it.** The dispatcher wrote the
  user's envelope on every turn, so a regenerate - which sends the thread back
  ending at the same user message - put that id in the log twice, and
  assistant-ui refused to build a thread that names one message twice. It now
  appends through `append_user_message_once`, which reads the log first and
  writes nothing when the id is already there, and the id decides rather than
  the client's `trigger`, as section 12.3 requires
  ([one id names one message in the log](decisions/one-id-names-one-message-in-the-log.md)).
  Four conversations on the dev database already held a repeat, so
  `reduceSnapshot` keeps the first message an id names and drops a later one:
  the reported conversation's 1,624-chunk log rebuilds as three messages, one
  question and both answers, with no repeated id. A unique index and a repair
  pass were both rejected, because neither can be applied to a log that already
  repeats an id without editing what was said. `ChatView` also wraps its body
  in an error boundary, so any thread that throws renders the error and a
  site-scoped way back to the conversation list instead of an application-error
  page.

* **MCP program batch G: an assistant that is not PathFinder answers with tools
  served over the network, and the program is reconciled.** `site_help`
  declares one source - two catalog reads and one control-test measurement from
  `veupathdb-wdk-mcp`, `required=False`, so a deployment that admits no such
  server still serves the assistant - and reaches it through its own typed
  per-turn channel rather than a widened runtime factory, because the graph is
  compiled before the turn's sources resolve
  ([a declared source reaches a one-agent assistant through its deps](decisions/a-declared-source-reaches-a-one-agent-assistant-through-its-deps.md)).
  A site-help turn driven through the worker answered from a tool the wdk-mcp
  container served over the compose network, and the source's one writing tool
  parks a card that the next request's answer runs - which is the program's
  whole claim: an assistant declares a source and the runtime does the rest.
  Two runtime defects are backlog items, neither in the source path:
  `single_agent_graph` builds every run from `state.user_prompt` alone, so a
  one-agent assistant forgets the previous turn; and a resumed approval turn
  emits `tool-input-available` with no `tool-input-start`, which the strict
  client tolerates and PROTOCOL 6.2 does not describe. A third finding - a
  suite-order red blamed on the runtime - was disproven by the review: the
  test double's in-process uvicorn installed process signal handlers that
  latch sse_starlette's process-global shutdown flag; the double no longer
  captures signals, and the ladder is order-independent again.

  The closing sweep found the bundle already honest: the six items the program
  touched are deleted or edited to their residual, the backlog index and its
  directory agree file for file, and every decision the program recorded is
  indexed. The three dated documents that outlived their claims are annotated,
  not rewritten. The execution plan's status line reads executed and points
  here; the design document's section 8 and appendix B carry dated notes, since
  four of appendix B's seven findings have closed and one of them closed before
  the program began; and the platform assessment's addendum carries the WS4
  entry with the two corrections its own debts paragraph needed - a failed turn
  is visible after a reload, and the max-lines gate is red on two modules
  rather than five.

* **MCP program batches E and F: the suite a foreign team can run, and the
  packages publish alone.** `assistant-platform/packages/mcp-conformance` ships 32 checks in six
  families as a pytest plugin that never imports pathfinder or
  assistant_core, proven by fifteen planted defects that each name their
  exact failing checks; run against our own served endpoint it answers
  `incomplete` honestly - 26 passed, none failed, six unsettled checks
  pinned by name - and its first real run surfaced three defects
  (an ortholog vocabulary shape the domain model refuses, an abandoned slow
  call that outlives its client and OOM-kills the server, the file-size gate
  red at HEAD), each now a measured backlog item. Nightly, CI and pre-commit
  lanes carry it. On the packaging side, assistant-core shed its last
  product dependency and installs into a clean venv with pathfinder absent;
  the client builds a dist whose tarball proves the three rings (core and
  legacy import with zero dependencies, the ai-sdk ring requires `ai` and
  only `ai`); `data-turn-failed` joined the protocol at 1.3.0 so a reloaded
  thread finally says the turn died, deduplicated against the live error
  card; and the task card left the per-task SSE dialect - the thread carries
  the whole lifecycle, the reattach fires at task start because a
  completion-fired design is provably impossible, and the fan-out lane
  collapse that removal exposed is a filed item, not a surprise. One review
  round each: the conformance dev-dependency had broken the api image build
  (three COPY lines), and one spec header still described the deleted
  subscription. Fable review: both accepted.

* **MCP program batch D: veupathdb-wdk-mcp is served.** Sixteen tools over
  streamable HTTP in a container of their own on the api image, binding in
  about three seconds because the entrypoint preloads nothing. Fourteen
  declare readOnly; the two writers declare non-destructive with per-tool
  `_meta` call budgets the live suite enforces by setting the client's
  read timeout from the served declaration - enrichment measured 508.9 s at
  the 200-gene cap against its declared 600, and the controls estimate held
  at under nine seconds against 180. Bearer auth chains the SDK's own
  middleware (the fastmcp shortcut silently drops the credential subclass,
  so the SDK path is pinned by a test that fails without the context
  middleware). Memory ceilings landed on the two growers (worker and
  wdk-mcp at 2 GiB, the api uncapped by measurement); sizing them
  reproduced the api OOM incident on purpose, and the live proof then
  showed a cold-site catalog read killing the served container at
  3.269 GiB - the eviction half stays in the backlog for batch F. The
  isolation case ran against a real foreign-owned public strategy and
  leaked neither the step nor its count. One review round: the server
  advertised fastmcp's version as its own; it now declares the
  deployment's, pinned at build and on the wire. Fable review: accepted.

* **MCP program batches B and C: the tool protocol lives in the runtime, and
  the sixteen tools' service seam exists.** `assistant_core/mcp/` now holds
  declarations, admission, the deny-by-default approval predicate, the
  untrusted-output wrapper with real jsonschema payload validation, the fixed
  wrapping order, and per-turn resolution: a declared source is built,
  credentialed at the transport and nowhere else, opened with the turn and
  closed with it, proven against an in-process FastMCP server with the
  design's P1 exit criteria each named in a test. The turn runner enters the
  resolution around the drive; a spec that declares nothing constructs
  nothing. The three sub-agents left their module singletons for
  per-dispatch factories. On the service side, the four gated catalog tools
  split into pure retrieval halves under `services/catalog/` with
  byte-identical wrapper behaviour pinned, `pathfinder/mcp/` gained bearer
  auth that reuses the api's verifier by identity plus the RFC 9728 document
  from the SDK's own helpers, and `enrich_gene_ids` runs enrichment by value
  through the same WDK plugin machinery with the wire field names pinned
  three ways. Fable review: both batches accepted with zero defects; the
  next batch inherits two measured corrections (the api venv lacks the
  fastmcp server extra, and the enrichment tool cannot fit the default
  60 s call budget).

## 2026-08-24

* **MCP program batch A: the trust base.** Three changes an external consumer
  of the runtime depends on, executed from the plan in
  `docs/design/2026-08-24-mcp-sdk-execution-plan.md`.

  **Every named tool is callable.** The gene chain VERIFY's instructions
  order (`literature_search`, `lookup_gene_records`,
  `resolve_gene_ids_to_records`) is registered on its toolset, the two
  catalog tools joined FRAME, and `update_search_decision` is deleted with
  its module. An agreement suite now walks every agent's instructions and
  the extractor registry and asserts each named tool is callable by that
  agent - it caught a fourth instance on EXECUTION and seven extractor
  orphans on the way, and the orphaned `SearchOverview` selection fields it
  exposed are a backlog item.

  **The deferred-tool cycle exists once.** The Lead's duplicated approval
  code folded onto `assistant_core.graph.approvals`: `parked_call` is the
  one construction of the shared fields, the Lead adds its product fields by
  `model_copy(update=...)`, and its thirty approval tests pass unchanged.
  The two resume helpers this file's earlier entry placed in `_lead_turn.py`
  now live in the runtime; the Lead keeps sub-agent re-entry, the
  dispatch-answer fan-out and `is_pure_approval` only.

  **The checkpoint allowlist is real.** It never was: with strict msgpack
  off, `with_msgpack_allowlist` returns the serializer unchanged, so every
  declared type was discarded and both hypotheses in the backlog item were
  wrong (the item leaves with the correction that `astream` warned
  identically). The serde now binds the allowlist at construction
  (decision recorded), `CombineOp` completes the PathFinder list, and an
  integration test reads a real thread under the library's serde-event
  listener and asserts zero unregistered-type events. Found on the way and
  filed: the api and package lockfiles resolve `langgraph-checkpoint` to
  4.0.1 and 4.2.0 under identical pins, and two api integration tests fail
  under machine load only.

* **Every tool an instruction or an extractor names is callable by the agent
  that reads it.** VERIFY told the model to resolve control gene IDs through
  `literature_search` then `lookup_gene_records` then
  `resolve_gene_ids_to_records`, and its toolset held none of the three, so a
  controls-needing verification spent a model turn on a tool that did not
  exist; all three are registered now. FRAME registers
  `browse_search_categories` and `list_transforms`, which the context extractor
  already claimed observations from. `update_search_decision` and its module
  are gone, superseded by the `set_criterion` flow, and the outage-rejection
  detector that was its only reader goes with them. A new agreement test walks
  each agent's instruction text and the extractor registry against the tools
  its toolsets register; it found a fourth case nobody had reported, EXECUTION
  naming `get_estimated_size` and `get_sample_records` under "Read-only
  inspection" while registering neither. The backlog item leaves with the fix;
  a new one records the six selection fields on `SearchOverview` that the
  deleted tool was the only writer for.

* **A rehydrated thread can keep talking: the request parses the protocol's
  own reduction output.** The snapshot reduction attaches `errors`, `aborted`
  and `finishReason` to an assistant message, and a live stream records
  `resultProviderMetadata` on an output-error tool part; pydantic-ai's strict
  message union refused both on resend, so any conversation whose history was
  rehydrated - a reload, a restore from dismissed, a branch - answered every
  later send with a 422 and the raw error list. `ChatRequestBody` now parses
  those members away in one before-validator, PROTOCOL.md 1.2.2 says a runtime
  MUST ignore them, and the restored-strategy e2e journey proves the turn end
  to end on a rebuilt stack. This closes the resend-brick investigation from
  the 2026-08-17 UI run; its backlog item leaves with it. `site_id` on the
  same body gained the String(50) bound the transport sweep gave every other
  request field.

* **The e2e mocks now speak the wire they test.** Five route-mocking specs
  sent `data:`-only SSE frames that section 3 of the protocol orders a client
  to reject, and parameter-sweep still spoke the pre-v6 `messages/partial`
  dialect against a dead per-task mock; all six now build their streams from
  one conformant fixture (`e2e/fixtures/sse.ts`) and pass. The "durable path
  never fires" scare dissolved with them: no e2e spec drives a real durable
  turn by design, and that coverage lives in the backend integration suites.
  What remains of the fourteen reds is worker contention on three feature
  specs that pass standalone, recorded with the adjudication in the residual
  item.

* **Every transport request string that lands in a bounded column is bounded.**
  One `SiteId` type now covers the five schemas the re-review flagged and the
  nine more a residual sweep found - body fields, write-path query params via
  `RequiredSiteIdQuery`, the auth routes' defaulted params - plus the gene-set
  and control-set name/searchName/recordType/source fields, each sized to its
  column, so an oversized value answers 422 at the edge instead of 500 at
  INSERT. Seventeen red-first cases pin the bounds; the spec and generated
  types carry them.

* **The stalled-turn releaser and the thread log survived their review.** The
  P2 verifier's findings, closed the same day: `_chat_stream_is_open` now
  reads only turn-tagged rows, so task progress written into the gap between
  turns neither reopens an ended turn nor hides a stalled one; `_ThreadLog`
  clears its pending update only when it wrote that update, so a concurrent
  scoped child's offer is no longer dropped while an append awaits the
  database; the first chat POST of a fresh test process paying the PIGuard
  model load against a 5 s enqueue ceiling is a backlog item with the
  measured runs.

## 2026-08-23

* **WS-V batch P1: the one-agent assistant can ask, and the loop guard finally
  runs.** Two mechanisms the runtime declared and never reached are now wired,
  each with the turn that proves it.

  **Approvals.** `single_agent_graph` admits `DeferredToolRequests` as a
  per-run output type, so a tool marked approval-required no longer reaches the
  user as "`DeferredToolRequests` is not among output types". The cycle lives
  in `assistant_core/graph/approvals.py` - park the call as a `PendingApproval`
  with the run's full history, rebuild `DeferredToolResults` from the user's
  answer, replay that history, and hand the emitter the hint that re-announces
  the call - and the graph runs it in about thirty lines. The phase a one-agent
  turn parks is `"agent"`, the name of the only node that can raise one; a
  one-agent assistant has one role and it is the graph's. A turn that answers
  nothing supersedes the card rather than re-running the call the user never
  approved. Nine package cases drive request, approve, deny, the parked state
  and the superseded card end to end, and three more do it over HTTP in
  `apps/api` with a site-help-shaped assistant whose one tool needs confirming,
  through the route, the worker and the resume. `site_help`'s own tools are
  read-only and stay silent.

  **The repetition guard.** `ToolRepetitionGuard.check` had no caller since
  batch C. It now runs from `RepetitionGuard`, an `AbstractCapability` the
  driver passes per run, on the guard the turn's deps carry - the same
  interception surface `ToolResilience` uses, chosen because the Lead's tools
  are registered with `tools=` and no toolset wrapper can see them. Both
  blocks return the refusal as the tool's ordinary result, never as a
  `ModelRetry` (a retry raised in the wrapper shares the tool's retry budget
  and can abort a run whose tool already retried); the first names the
  repetition so the model can route around it, the second sets
  `stopped_call_id` and the driver stops consuming the stream once that
  result has reached the client, so the turn ends with `finish`/`stop` and no
  dangling part. It is
  wired on the Lead, the three sub-agents and the single-agent graph, and the
  synthetic assistant grew a loop arc that asks for one reading five times: the
  third is refused, the fourth ends the turn, and the fifth is never made.

  Two things the wiring found. `graph_modifying_tools` was a constructor
  argument with no behaviour - both of `check`'s early branches reset the
  counter and return `None` - so it is gone and a tool outside the vocabulary
  is what clears a streak. And `READ_ONLY_TOOLS` named ten tools, nine of which
  no agent has carried since the FRAME/BUILD/VERIFY split; the guard would have
  watched `get_plan` and `search_catalog` forever. It now names the 26 real
  inspectors across the four agents, and a seam test fails when a watched name
  is not a tool some agent offers.

  `PROTOCOL.md` is **1.2.0**: section 6.2 states the approval cycle a turn
  really runs, the `error` example the reference assistant used to produce
  because of this defect is gone, and `tool-approval-request` is captured in
  its place. `@pathfinder/assistant-client` re-synced and its reducer already
  read both chunks; two conformance cases now say so. Devtools' loop diagnosis
  reports guard refusals, and one refusal is enough to name a loop, because the
  guard measured it rather than inferring it from a failure count.

  `lead_node.py` crossed the 400-line cap on the way, so model selection left
  it for `_lead_model.py` and the two approval-resume helpers joined the rest of
  the Lead's approval code in `_lead_turn.py`; the five known files are the only
  ones over the cap again.

  Verified: package `uv run pytest` 205 passed with no `pathfinder` installed,
  ruff, ruff-format, mypy --strict 54 files; `apps/api` ruff, mypy --strict 577
  files, pyright 0/0/0, import-linter 7 kept, 2626 unit tests, the integration
  suite; the client's 200 vitest cases; `openapi check` exit 0 and `yarn tsc`
  clean on the web app; knowledge gate 120 files.

* **The protocol grew a request side and stopped needing two readers.** PROTOCOL.md
  1.1.0 answers the two questions section 6.4 of the MCP/SDK design named as ours to
  close before an external client is written. The turn-start contract is section 12:
  the identity a request must prove, the `X-Requested-With` rule that applies to a
  cookie and not to a bearer, the body split into the nine fields any assistant on
  this runtime takes and the one this product adds, the approval answer that rides in
  the body instead of inventing a user message, the six refusals including the `409`
  a thread's fixed assistant produces, and the fact that the POST's response is a tail
  from the last turn terminator rather than a stream the turn depends on. Two request
  examples are on the page and a gate validates both through `ChatRequestBody`; a
  second gate asserts the two field tables together name every field the model
  accepts, so a field added without a row on the page fails.

  The durable-task half is its own subsection of section 6.
  `data-background-task-started` was already in the log; `data-task-progress` and
  `data-task-completed` are now written there too, untagged, so the chat stream
  carries them and a client that reads the thread learns the whole lifecycle with one
  reader and one cursor. Progress is coalesced - first
  update, every five-point advance, ten seconds of silence, and always the last one -
  because the alternative is on the order of 900 rows replayed on every read of a
  thread that once ran a sweep. The comparison is in whole percentage points, since
  `0.15 - 0.10` is `0.049999999999999996` and a fraction rule would skip the tick it
  names. The chunk carries the task id as its `id`, so however many are written the
  reduced message holds one part.

  The per-task endpoint keeps working byte for byte and is now written down rather
  than merely known: section 13 states its `event: stream` framing, its `custom`
  envelope, its missing cursor and the two payloads that differ from their logged
  counterparts, and an integration test pins its exact frames against that section.
  It is deprecated, `@pathfinder/assistant-client/legacy` says so, and the web app's
  migration is a backlog item rather than a break.

  All three gates were made to bite before they were trusted. Removing the
  `phaseReasoning` row from the document's core table failed the field-table test with
  "Extra items in the right set: 'phaseReasoning'"; adding one space inside the pinned
  legacy frame failed the golden test on that byte; renaming the changelog's newest
  row failed the new assistant-core test with `assert '1.2.0' in {'1.0.0', '1.1.0',
  '1.2.1'}`. All three were restored.

* **The published OpenAPI spec is the production contract, whatever the process environment.** `openapi check` answered 0 or 1 depending on who ran it: the generator built the app under the ambient profile, so a mock-profile shell put `/api/v1/dev/login` into `packages/spec/openapi.yaml` and a production shell then reported drift. `create_app` takes `include_dev_routes` (None follows settings; the generator passes False), the committed spec is regenerated without the dev route, and a unit test pins that a mock-profile environment still produces a spec with no `/api/v1/dev/` path.

* **WS-V batch 4: the eval system, and the consent that feeds it.** Consent is
  `users.eval_data_consent`, default on, with `eval_notice_seen_at` beside it so the
  one-screen notice is shown once per account rather than once per browser; both are
  read and written through `GET`/`PATCH /api/v1/me/privacy`. The notice renders over
  the app and is dismissible - Escape, the backdrop, **OK**, or the inline **Turn off**
  that opts out and records the notice in one call - and Settings gained a **Privacy**
  tab whose toggle disables and re-enables. Extraction is a daily `maintenance` task
  that reads finished threads of consenting users, strips email addresses and URL
  credentials, and writes `eval_staged_cases`; `EvalExtract` refuses to be constructed
  if either pattern survives, so an unredacted candidate cannot be queued. Curation is
  `pathfinder.devtools.evals`: `staged`, `show`, `promote`. A promoted case is a JSON
  file under `apps/api/src/pathfinder/evals/corpus/`, on the manifest-and-provenance
  shape the WDK fixture store introduced in batch 3. Every chunk in the extraction
  suites is built by the code that writes it to the log - `user_message_chunk`,
  `TextDeltaChunk`, `ledger_update_event` - so a renamed chunk kind fails the tests
  instead of quietly emptying the queue.

* **The linkage rule became a check constraint.** "Extraction severs user linkage" and
  "an opt-out clears the user's staged items" cannot both describe the same row, so the
  linkage was given a lifetime instead: a staged row names its user, its thread and its
  extract; promotion nulls all three and keeps the content hash, the corpus name, the
  site and the assistant. Any other combination is unwritable, and the foreign keys
  cascade, so deleting an account removes its staged rows with no code running while
  promoted cases are already out of reach. `DELETE /api/v1/user/data` reports
  `stagedEvalCases` beside its other counts. Recorded as
  [a staged eval case carries its user until promotion](decisions/a-staged-eval-case-carries-its-user-until-promotion.md).

* **The harness is pydantic-evals, and the promotion policy is written down.** The spike
  found `pydantic-evals` **2.22.0** already installed as a hard dependency of the pinned
  `pydantic-ai`, providing the dataset, the case loop, the evaluator protocol and the
  report; the run summary stays a local model so the SLI feed does not follow a library's
  dataclass. Four cases encoded from the cataloged UI-run failures ran **4/4 green in
  32.7 s** against the deterministic provider, and a case given a wrong
  expectation fails with its named difference rather than silently. One
  extraction pass over the development database read 50 threads and staged **6**
  candidates across four sites. `conventions/verification-gates.md` now
  carries the ruled policy: an eval starts as a tracked trend, becomes a hard gate only
  after it catches or would have caught a real regression and holds stable, and a flaking
  gate is demoted or deleted, never suppressed. Recorded as
  [the eval harness is pydantic-evals](decisions/the-eval-harness-is-pydantic-evals.md).

* **Two deviations and one finding.** Four cases rather than ten: the deterministic
  provider routes on keywords, so a case whose red comes from a test-double marker
  reports a regression that is not there. Exact structural match rather than NTED: the
  only tree-edit-distance implementation in the repo is in the retired thesis harness and
  depends on `zss`, `numpy` and `scipy`
  (the graded distance landed on 2026-08-30, written in plain Python). And reading a thread through
  `graph.aget_state` prints eleven "Deserializing unregistered type" warnings, including
  for three types that are on the allowlist `assistant_core.conversation.serde` builds,
  where the same checkpoint read by `astream` prints none
  (fixed (`assistant-platform: docs/knowledge/decisions/the-checkpoint-allowlist-binds-at-construction.md`)).

## 2026-08-22

* **WS-V batch 3: the science verifies in two lanes, and the WDK rule bundle has one
  unenforced entry left.** Per-PR: 31 of the 32 untested rules became hermetic tests over a
  pinned fixture store, so `check-wdk-rules` reports **78 enforced, 4 partial, 1
  unenforced** where it reported 32 unenforced, and three `PARTIAL` entries closed with it
  (WDK-STRAT-002 in `veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`, `-003` and
  [WDK-MAP-003](wdk/pathfinder/rules/pathfinder-mapping.md), all three by one test that runs the
  projection to its third function and asserts on the serialized `WDKStepTree`). Nightly:
  `pytest -m live_wdk` collects **139** tests, skips cleanly with no credential, deletes
  every strategy and step it creates, and writes a JSON summary of outcomes, per-site
  tallies and drift. The recording path is `veupathdb.devtools.fixtures`: a
  declarative manifest of 12 exchanges, provenance stored as data rather than as a comment,
  and one command - `yarn wdk:record` - that refreshes the store a confirmed drift
  invalidates. The gate now fails a rule whose status is `UNENFORCED` and whose block
  carries no `reason`, so the column cannot fill with silence again.

* **Four defects the rules found, each in the code the rule anchors.**
  `get_duplicated_step_tree` parsed WDK's `{"stepTree": ...}` envelope with a model that
  declared no camelCase alias, so the only supported way to graft one strategy's branch
  into another raised on every call
  (WDK-STRAT-007, `veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`). `StepValidation` defaulted `level`
  to `NONE` and `is_valid` to `True`, and `WDKStep.validation` defaulted to that model, so
  a step document carrying no validation object at all read as a positive claim of
  validity - both defaults are gone, and an absent bundle is now `None`
  (WDK-VALID-001, `veupathdb-py: docs/knowledge/wdk/rules/validation.md`). A 4xx body was truncated to 200 characters
  and its `byKey` messages discarded, where a validating endpoint answers with a validation
  bundle; `integrations/veupathdb/_failures.py` now parses it and carries the per-parameter
  messages on the error (WDK-VALID-006, `veupathdb-py: docs/knowledge/wdk/rules/validation.md`). And a `date-range`
  bound in any format was accepted locally and sent to WDK, where a badly formatted one is
  a **500** that names nothing (WDK-PARAM-006, `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`);
  a bound is now an ISO date or a local refusal. `step_status` also read `is_valid` without
  its level, so a `NONE` bundle - which WDK emits as `isValid: false` - read as INVALID.

* **The hidden-defaults sweep ran, and the answer is smaller and sharper than the question.**
  On plasmodb.org, **237** of 359 transcript searches carry a hidden required parameter with
  a published default (182 of 325 on 2026-08-14). Binding every published default, 19
  answered 200 and **exactly one returned zero rows**:
  `GenesByRNASeqpfal3D7_Lee_Gambian_ebi_rnaSeq_RSRCWGCNAModules`, on `eda_dataset_id` and
  `wgcnaDataset`. Of the 158 refusals, **not one names a hidden parameter** - every
  parameter WDK named is visible, `samples_percentile_generic` 77 times - so no hidden
  default was refused, and what blocks the remaining measurement is the visible half of
  WDK-PARAM-010 (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`). `channel` (75 searches) and
  `dataset_url` (56) stay unmeasured for that reason, and
  the hidden-required-defaults item now carries the
  numbers instead of the question.

* **The lane's first run found seven dead live tests, and they are fixed.** Every
  `live_wdk` suite under `tests/integration/strategies/` read the persisted plan off
  `Conversation.strategy_ast`, which moved to `ConversationStrategy` when the runtime
  became a package. The tests skip without a credential, so nothing had run them since;
  under the account all seven raised `AttributeError`. They read the projection now, and
  the whole lane - 94 rule and sentinel checks plus the 45 that existed - is **139 green**.

* **One live drift, measured rather than assumed.**
  WDK-FILTER-006 (`veupathdb-py: docs/knowledge/wdk/rules/filters.md`) recorded a **400** naming the column when
  `byValue` is applied where the record-type document advertises it and the step will not
  take it. On 2026-08-22 the same four columns answer **500 `Internal Error`**, and
  `gene_product` still answers 200. The refusal holds, the diagnosis is gone, and a 500 is
  retried three times where the 400 was refused at once. Guest reads have also closed:
  `GET /record-types/transcript/searches/...` is a **401** without a registered token,
  which is why the recording command needs `VEUPATHDB_AUTH_TOKEN` and why the bundle's
  "most live checks need no credential" note no longer holds.

* **WS-V batch 2: the runtime proves the conversation works, and the wire has a written spec.** `assistant-platform/packages/assistant-core/tests/synthetic.py` is a complete `AssistantSpec` built from runtime code alone - `single_agent_graph` over bare `TurnState`, an `Agent` whose model is a `ScriptedModel` with four arcs (plain answer, `add` tool call, an approval-required `wipe_everything`, and a `stop_turn` that sets the cancel from inside the run), a `UsageLedger` as the `charge_usage` hook, and a `turn_epilogue`. The suite drives it through the package's public surfaces only, so 128 tests became **192**: turn lifecycle (the graph's chunks reach `conversation_events`, reduce to the `UIMessage` a client renders, and leave one `messages` row whose `usage.totalTokens` equals what the ledger was charged), durability (a reader that reconnects at cursor N gets the remainder **byte for byte**, cursors are strictly increasing and unique, the snapshot equals the live accumulation, two turns split cleanly on `done`), resume (a turn with `is_resume=True` names no prompt field at all, so `turn_input` omits it and the checkpointed prompt survives - the resumed turn answers from it), cancellation, cost, tenancy (two threads driven with `asyncio.gather` share no event id and neither sees the other's chunks), SSE framing against a real Postgres LISTEN channel (a strict `tests/sse.py` parser that accepts `id`/`data` frames and comment frames and nothing else), and a strict-msgpack round trip of every `CORE_CHECKPOINT_TYPES` entry plus the state type a spec declares - which the package could not prove alone before, because the only such suite lived in `apps/api`. **One real bug, found by the suite and fixed**: `_stream_answer` returned on the first event seen after the cancel was set, and pydantic-ai runs the agent in a background task that had already executed the tool and produced its `FunctionToolResultEvent`, so a stopped turn discarded a result it was holding and persisted the call in state `input-available` forever - a tool part that spins after a reload for a tool that finished. The rule is now *a cancelled turn ends before the next part the model starts*: the step already in flight reports its outcome, and the existing guarantee that no further model call is streamed is unchanged (`test_a_cancelled_turn_makes_no_further_model_call_and_finalizes` still passes beside the new `..._still_reports_the_tool_that_already_ran`). **One real gap, named not fixed**: the shipped turn graph resolves no deferred tool call, so `Tool(x, requires_approval=True)` on a one-agent assistant produces `tool-output-error` plus an `error` chunk reading "`DeferredToolRequests` is not among output types" instead of a `tool-approval-request` card, and `TurnState.pending_approval` is a channel no turn ever writes; PathFinder's Lead implements the cycle, `assistants/site_help` cannot - a backlog item with the fix and the chunk sequence it would produce (closed in WS-V batch P1). **`assistant-platform/PROTOCOL.md` is version 1.0.0** of the wire: frame grammar, cursor semantics (`after` is exclusive, cursors are per-deployment and not dense), the snapshot/tail contract and the `204` fallback, the `start ... finish done` turn shape, the three `finishReason` values and the rule that an `error` chunk does not end a turn, the full chunk vocabulary, the reduction rules, and the additive-only versioning rule. Its examples are captured from real turns and its tables are compared to `register_core_stream_parts` and to pydantic-ai's `vercel_ai.response_types`, so a new chunk kind or a changed payload fails `test_protocol_document.py`; only generated ids and instants are edited. Recorded as the wire protocol is a written spec, verified against captured frames (`assistant-platform: docs/knowledge/decisions/the-wire-protocol-is-a-written-spec.md`), which names the rejected alternatives: generating the page from the models (true by construction, and with nowhere to put a rule) and leaving it hand-written (silent drift). **Where the boundary cuts**: `run_turn`, the cancel watcher that polls `chat_turn_cancellations`, the durable-tool interrupt stream, the title generator, `identity_gate` and the user-message envelope all live in `apps/api`, so the suite composes their package-side equivalent in `drive_turn` (start chunk, `astream`, epilogue, finish, done) and says so; `turn_epilogue` is exercised, `identity_gate` is not reachable without a transport. `docs/knowledge/conventions/verification-gates.md` gained the package lane. Verified: from the package, `uv run pytest` 192 passed with `find_spec("pathfinder") is None`, ruff over `src tests`, ruff-format, mypy --strict 53 files; from `apps/api` - untouched this batch - ruff, ruff-format, mypy --strict 557 files, pyright 0/0/0, import-linter 7 kept 0 broken, 2392 unit and 379 integration tests, `python -m pathfinder.devtools.openapi check` exit 0; knowledge gate clean at 110 files. No file under `apps/web/` was touched.

* **WS-V batch 1: the runtime is a package, and the boundary is now an installation fact.** `assistant-platform/packages/assistant-core` is its own distribution - own `pyproject.toml`, own `uv.lock`, `src/assistant_core` importable with no `pathfinder.` prefix, own `tests/` tree, own CI job - and `apps/api` consumes it as an editable path dependency beside `pathfinder-shared`. The eleven-module surface that batch D pinned as "what the runtime may reach outside itself" moved with it, because every entry was runtime-owned by nature: `platform/{config,context,db,logging,pydantic_base,types}.py`, `integrations/embeddings/{model,prefixes}.py` (now `assistant_core/embeddings/`), and the four tables the runtime reads and writes - `conversations`, `messages`, `conversation_events`, `memory_tombstones` - with `MessagesRepository`, `MessageMetadata`, the `GUID` type, the application-id column and the declarative `Base`. **Three modules split rather than moved, each along what it imports**: `config.py` became `RuntimeSettings` (database URL, engine echo, SSE keep-alive, log level and format) in the package with `Settings` subclassing it in the product and installing itself through `use_settings_source`, so one instance still serves the process and `get_settings.cache_clear()` still works in tests; `context.py` kept `veupathdb_auth_token_ctx` and `request_base_url_ctx` product-side and moved the six the runtime and its logger read; `db.py` moved the engine, the session factory and the request-scoped session, and left `init_db` - which runs alembic against `alembic.ini` - as `platform/migrations.py`. `errors.py` and `principal.py` stayed, because their taxonomies name WDK, VEuPathDB bearers and PathFinder service tokens; the one thing `db.py` took from `errors.py` was a sqlite guard, which now raises `ValueError` with the same detail (both reach the client as a 500). **One declarative base, not two metadatas.** A cross-package foreign key resolves only inside the `MetaData` that holds both tables, and the keys cross in both directions (`conversations.user_id` and `conversation_events.task_id` point at host tables; `conversation_strategies`, `background_tasks`, `chat_turn_cancellations` and the two scratchpad tables point back at `conversations`), so the package exports `Base` and the product maps its twelve tables on it. `alembic/env.py` is untouched, `target_metadata` still lists all sixteen tables, and every migration stays hand-written. The package's own test kit declares stub `users` and `background_tasks` tables so `create_all` works with nothing else installed. **The thread lost its relationship to the science**: `Conversation.strategy` and `Conversation.strategy_view` named `ConversationStrategy`, which a package class cannot, so `ConversationRepository.get_with_strategy` and the two listings now select the thread beside its projection through one outer join (one query where `selectinload` issued two), `get_strategy` reads the projection alone, `get_owned_thread_or_404` returns both, and `build_conversation_response`/`build_conversation_summary` take the projection as an argument; `build_conversation_summaries` states the list mapping once. `Conversation.user` was deleted, because a package class cannot name `User`; `User.conversations` stayed as a **one-directional** relationship, because the unit of work reads it to insert a user before the thread that references it, and dropping it turned 22 integration tests into `conversations_user_id_fkey` violations. `TurnContextFactory` became `Callable[[TurnContextRequest], Awaitable[TurnContext]]`, because PathFinder's factory read `strategy_view` off the row it was handed and now has to read its own projection. **Contract 7 was replaced, not deleted twice over**: the package's pyproject names no dependency on this application (the enforcement), `tests/unit/test_package_boundary.py` walks every module in the package and fails on an import naming `pathfinder` while pinning the two `shared_py` wire-type modules it does read (the belt), and the seventh in-repo contract now says *the science never imports an assistant's composition root* - direct-only, like the six layer contracts, because the chat dispatcher still reaches the registry through the job runner. `test_core_boundary.py` moved to composition level and reads the installed distributions instead of the import graph: the science requires the runtime, the runtime requires no part of the science, and the two source trees do not nest. Recorded as [the runtime is a package, so the boundary is an installation fact](decisions/the-runtime-is-a-package.md), which names the rejected alternatives: keeping the runtime in-repo behind contracts only, and leaving `conversations` product-side. Verified: `cd assistant-platform/packages/assistant-core && uv run pytest` passes 128 tests with **no `pathfinder` installed** (the isolation proof, testcontainers Postgres, `importlib.util.find_spec("pathfinder") is None`), plus its own ruff and mypy --strict (53 files); from `apps/api`, import-linter 7 kept 0 broken, ruff, ruff-format, mypy --strict (557 files) and pyright zero findings, 2771 tests green in one run (2392 unit, 379 integration, 50 skipped, 98 subtests), `packages/spec/openapi.json` byte-identical, the file-size gate reporting the same five known files (it now scans the package too), and the knowledge gate clean at 108 files. No file under `apps/web/` was touched.

* **WS3 batch 2: a second assistant answers through the same runtime, and its diff contains no orchestration.** `pathfinder/assistants/site_help/` is 3 modules - a spec, one pydantic-ai agent with two read-only catalog tools (`list_veupathdb_sites` over `services.catalog.sites.list_sites`, `describe_site` over `get_record_types` plus `get_raw_searches` for the per-record-type search count), and a ScriptedModel script - registered beside PathFinder in the one registry. It declares `TurnState` with no domain field, a bare `TurnContext` with no strategy session and no research clients, no stream parts, no memory kinds, no checkpoint types, no turn epilogue and **no identity gate**, so a signed-in application user with no VEuPathDB login is served; PathFinder's 401 `WDK_LOGIN_REQUIRED` on the same route with the same body is re-asserted byte for byte in the same test file. A boundary test walks the pilot's modules and fails on a single import of `pathfinder.ai`, and pins the eleven modules it does reach. **Lifted into core to serve it, each because the single-agent path needed it and none of it names a product**: `cost_for_run` moved from `ai/cost.py` to `assistant_core/cost.py` (token-to-USD is the runtime's accounting, and the module imported only `genai_prices`); the chunk-emit primitive became `assistant_core/graph/emit.py`, which also collapsed the two identical copies `_lead_capture.py` and `sub_agent_stream.py` each carried; and the assistant-message write became `assistant_core/graph/turn_message.py`, which read no PathFinder field before the move and now guards its own `SQLAlchemyError` so both finalize paths inherit it. `ScriptedModel` scripts may return a `TextPart`, because an agent whose output is prose has no `final_result` tool to call. `assistant_core/graph/single_agent.py::single_agent_graph` compiles the reusable turn graph: it streams the agent's text and tool calls through the same `PhaseStreamEmitter` the Lead uses, accumulates `RunUsage` into `turn_total_tokens`/`turn_total_cost_usd`, stops on the turn's cancel event without a further model call, and ends in the runtime's finalize step. It compiles **two** nodes, not one: the message row is reduced from chunks the durable log only holds after the agent's step has ended, so a same-node finalize would race the writer. Quota persistence stays product-side - `services.quota` is forbidden to core by contract 7 - so the helper takes the charger as a declared hook and the pilot's turns count against the same monthly budget. The pinned core surface grew by exactly `persistence.repositories.message` and its `_message_metadata`. **Creation paths**: `POST /api/v1/conversations/{id}/begin` takes an optional `assistantId` with the chat route's semantics (new thread takes it, existing thread keeps its own, mismatch 409, unknown 404) and the seed-title generation now uses that assistant's mock rather than the default's; `devtools/chat.py` takes `--assistant`. Verified: import-linter 7 kept 0 broken, ruff, mypy strict (596 files) and pyright zero findings, 2489 unit and 388 integration tests, openapi drift additive only (`BeginConversationRequest.assistantId`), types regenerated, `tsc --noEmit` and 2177 vitest clean, file-size gate reports the same five known files.

* **WS3 batch 0/1: the assistant declares its own architecture, and the runtime routes to it.** `assistant_core/spec.py::AssistantSpec` is a frozen model with `assistant_id` and eight declarations - a graph factory (`checkpointer -> CompiledStateGraph`), an initial-state factory (`TurnStart -> TurnState`), a turn-context factory (`TurnContextRequest -> TurnContext`), a mock-model factory, `checkpoint_types`, a stream-part hook, `memory_kinds`, an identity gate and a turn epilogue - and each one replaces something the pipeline previously hard-coded about PathFinder: `build_pathfinder_graph` named by four processes, `_build_turn_input`'s dict, `_turn_helpers._build_runtime_context` with its two stub research clients, `title_generator`'s `get_mock_model` import, the import-time `register_checkpoint_types` call in `ai/graph/state.py`, `_stream_parts_schemas`'s direct `register_strategy_stream_parts`, `PRODUCT_MEMORY_KINDS`, the chat route's `require_registered_wdk_identity` dependency, and `turn_runner._emit_strategy_revision`. The spec module imports `persistence.models` and `platform.types` and nothing else outside core, pinned by an extension to the core-surface test; `pathfinder.assistants` joined contract 7's forbidden list, so the runtime cannot reach the composition root either. `pathfinder/assistants/` builds PathFinder's spec from the existing `ai/` pieces and `registry.py` is the one composition root that main, the worker, the durable-resume runner and devtools consume. **Routing**: `conversations.assistant_id` (`NOT NULL DEFAULT 'pathfinder'`, indexed, alembic `2026_08_22_0001`, both directions tested against a real database) is the record; an optional `assistantId` on the chat body is read only when the thread is created, an unknown id is 404 `ASSISTANT_NOT_FOUND` and naming another assistant on an existing thread is 409 `ASSISTANT_MISMATCH` rather than a silent substitution - a caller that believes it is talking to B and reads A's answers has no way to notice. The `ChatTurnPayload` carries the resolved id to the worker and `jobs/runner.py` reads it off the row on a durable resume; `dispatch` re-checks the row `begin_conversation` returned against what it resolved, so a concurrent first turn that created the thread under another assistant is refused rather than deferred under the wrong one. **Identity**: the chat route's gate is now `resolve_chat_assistant`, a dependency that resolves the assistant and runs `spec.identity_gate` when one is declared; PathFinder declares `require_registered_wdk_login`, so the refusal is the same 401 `WDK_LOGIN_REQUIRED` with the same title and detail, and `test_wdk_login_required.py` passes untouched. The route table gained a `SPEC_GATED` section with the reason and two cases that fail if the chat route ever carries both gates or stops resolving an assistant. The state factory returns a model and the runtime sends only `model_fields_set`, so an approval resume still leaves the checkpointed prompt alone. Recorded as [the orchestration belongs to the assistant, not to the platform](decisions/the-orchestration-is-the-assistants.md), which names the rejected alternative: one platform graph parameterized by config, rejected because a config-shaped Lead is still a Lead - a simpler app declares a different graph, not a defanged one. Verified: import-linter 7 kept 0 broken, ruff, ruff-format, mypy strict (594 files) and pyright zero findings, 2460 unit and 380 integration tests (98 subtests), openapi drift additive only (`ChatRequestBody.assistantId`, `ConversationResponse.assistantId`, two `ErrorCode` members; the chat request body `$ref` is byte-identical), types regenerated, `yarn tsc --noEmit` and 2177 vitest clean, knowledge gate clean.

* **WS2 batch D: the assistant runtime is a directory, and a contract keeps it one.** The last batch of the platform program (`docs/superpowers/specs/2026-08-21-ws2-in-repo-seams.md`) moved the runtime-generic modules into `apps/api/src/pathfinder/assistant_core/` - 25 modules across `capabilities/`, `conversation/` (chunk reducer, AI SDK adapter, event writer and stream, checkpoint serde and saver, stream-part registry), `graph/` (`TurnState`, `TurnContext`/`AssistantDeps`, the pre-turn and agent-factory hook types, the runtime chunk builders), `memory/` and `models/scripted.py` - and 210 references in 106 files followed, with no alias and no re-export shim. Membership was decided by walking each candidate's transitive imports, not by its name: what reaches nothing of PathFinder's moved, and what does not stayed and is named below. Three files held both halves and split along the line batch A drew: `ai/graph/runtime.py` (`TurnContext`/`AssistantDeps` to core, `Context`/`AgentDeps`/`build_node_deps` product), `ai/graph/stream_events.py` (the chunk builders whose kinds the core registry registers to core; enrichment, strategy revision and ledger stay product), and `integrations/embeddings/semantic_index.py`, whose fastembed singleton was the runtime's only indirect route to a WDK type and is now `integrations/embeddings/model.py` - the cache key still hashes the same model-name string, so no stored `.npz` row was invalidated. `PreTurnHook` and `TurnAgentFactory` became PEP 695 generic aliases bound to `TurnState`, `TurnContext` and `Agent`, so core states the hook shape and `builder.py`, `lead_node.py` and `composition.py` name `PipelineState`, `Context` and `LeadAgent` at the call. **Contract 7** (`The assistant runtime never imports the science, directly or indirectly`) is the only one of the seven that also rejects indirect chains, because a runtime that reaches the science through one hop is not a runtime a second assistant can take; it was proved to bite by planting `from pathfinder.ai.graph.state import PipelineState` in `event_writer.py`, which it reported both as a direct violation and as a two-hop chain to `pathfinder.domain.strategy.staleness`. What stays reachable is the whole allowed surface and nothing else - `pathfinder.platform`, `pathfinder.persistence.models`, `veupathdb_mcp.embeddings` - pinned as an exact set by `tests/unit/test_core_boundary.py`, which caught its own batch when the `ReasoningEffort` de-duplication added `platform.types` to it. That de-duplication collapsed three identical `Literal["none", "low", "medium", "high"]` declarations (`graph/runtime.py`, `conversation/request_body.py`, `platform/types.py`) onto the platform one. Left product-side deliberately, with the blocking import named: `ai/graph/builder.py` names `make_lead_node` and `finalize_turn_node`, and injecting a graph's node set is a seam this batch did not design; `ai/conversation/dispatcher.py` defers `jobs.tasks.run_chat_turn_job` and opens the thread through `services.conversations.begin`; `turn_runner.py` and `_turn_helpers.py` reach `services.conversations.responses` and `graph.runtime.Context`; `request_body.py` publishes `PhaseRole`; `title_generator.py` calls `get_mock_model()`. Recorded as [the assistant runtime is a package boundary, not a contract over scattered modules](decisions/assistant-core-is-a-package-boundary.md), which names the rejected alternative: a contract over a module list with no move, which leaves the extraction an archaeology exercise over a 100-file tree. Verified: import-linter 7 kept 0 broken, ruff, ruff-format, mypy strict (587 files) and pyright zero findings, 2423 unit tests (33 of them the new boundary cases) and 369 integration tests with 98 subtests, `packages/spec/openapi.json` byte-identical, the knowledge gate clean at 105 files, and no file under `apps/web/` or `packages/` touched.

## 2026-08-21

* **WS2 batch C: the runtime hard-codes nothing of PathFinder's any more.** The seven pluggability entanglements (assessment Appendix A rows 5, 6, 7, 9, 12, 13, 14) are inverted. **Roles**: `TurnContext.phase_models`/`phase_reasoning`, `resolve_phase_tier_config`, the agent registry and `PendingApproval.phase` all take a plain string; `PhaseRole` survives only in `ai/agents/roles.py` and the three models that publish it, and `SUB_AGENT_APPROVAL_PHASE` moved to `ai/lead/sub_agent_tools.py`. **Pre-turn**: the live WDK staleness read left the turn node for `ai/lead/pre_turn.py` and reaches the graph as a required `pre_turn` hook. **Agent**: `lead_agent` is no longer a module singleton - `build_lead_agent()` is a factory the builder takes, so each turn owns its instance and its `override`; the dead `isinstance(agent.model, FunctionModel)` branch went with it. **Guards**: `ToolRepetitionGuard` and `ToolResilience` take their tool-name sets and thresholds as constructor arguments, with PathFinder's in `ai/agents/tool_vocabulary.py`. **Instructions**: `_instructions.py` keeps the two generic pinned renderers (typed on `AssistantDeps`); the system prompt, FRAME workspace, graph, ledger and discovered-searches renderers moved to `strategy_instructions.py`, byte-identical (pinned by a render digest before the move, then retired for a per-agent order contract). **Memory**: the store, retriever, tombstone index and re-embed all key by `str`; `auto_write_memories` takes candidates and a user id, so `ai/memory/` imports no product module at all, and `ai/lead/memory_candidates.py` owns the four kinds and the turn-to-candidates mapping. **Mock**: the reusable half (role markers, sequence advance, `FunctionModel` wiring, context vars) is `ai/models/scripted.py`; `mock.py` is PathFinder's script for it, with all 71 mock unit tests unchanged. One `build_pathfinder_graph` composition root replaced five duplicate `build_graph` call sites. Three copies of "read the model id off an agent" collapsed into `ai/models/settings.baked_model_id`, and `ConversationUpdate` left the conversation repository for its own module so the file-size gate reports only the five known files again. Recorded as [the runtime takes the vocabulary as an argument; the wire keeps it](decisions/vocabulary-is-an-argument.md) and [the Lead agent belongs to the turn that runs it](decisions/the-agent-belongs-to-the-turn.md). Found on the way and filed rather than fixed: the repetition guard is registered on no agent, so the mechanism this batch made injectable never actually runs (closed in WS-V batch P1). Verified: ruff, mypy strict, pyright and ruff-format zero findings, import-linter 6/6, 2390 unit tests (67 of them new seam tests), the integration suite, and `packages/spec/openapi.json` byte-identical - the frozen wire contract is what kept the three published role enums and `MemoryValue.kind` narrow.

* **The embedding cache holds one row per entry, and the encode no longer runs on the event loop.** The whole-file cache validated a site by hashing its whole catalog, so any drift in the fetched content re-encoded everything: the same api process built the portal index twice in one boot at 2472 and then 2934 entries, tritrypdb (414) and vectorbase (923) re-encoded hours after another process had written their npz to the shared volume, and a worker chat turn on the portal held the worker at 785% CPU for 2 h 39 m while every queued turn and the heartbeat waited. The cache is now content-addressed per entry: `SearchIndexEntry.cache_key` is a sha256 over the model name, the document prefix and the enriched text, the npz carries `keys` beside `embeddings` with the rows aligned to them, and `build()` reads the file as a key-to-row map, encodes only the entries with no row, assembles the matrix in the canonical `(record_type, search_name)` order from cached and fresh rows, and writes back exactly the current keys, so stale rows leave the file instead of accumulating. A catalog that drifts by N searches costs N encodes, where the portal's second build of that boot paid for all 2934. Files in the old `embeddings + hash` shape, the bundled ones included, read as a miss and are not converted, so each site pays one more full encode and only deltas after that. Two invalidations are automatic: the model name is inside the key, so a model swap invalidates every row, and a cached row whose width does not match the model's output re-encodes the site. Writes are staged under a pid-suffixed name and renamed into place because api and worker share the `embeddings_cache` volume, and a truncated file now reads as a miss rather than raising. Off the loop: `build()` is `async` and the fastembed call runs through `asyncio.to_thread`, which ONNX makes real work rather than a formality since it drops the GIL for the encode; `SearchCatalog._build_semantic_index` is the only caller and both of its call sites were already coroutines, so the seam is three awaited lines and no service changed shape. The turn that triggers a cold build still waits for its own index, but nothing else on the worker does. Eight unit tests pin it, including a delta encode that receives only the new entry's text, a removed entry that keeps the others and drops its key from the file, the old-format and truncated misses, the width miss, and an event-loop responsiveness test whose fake blocks inside `embed` on a `threading.Event` and fails if the loop cannot release it. Verified: ruff, mypy strict and pyright clean, 2351 unit tests.

* **WS2 batch B: a conversation is a thread again, and its strategy is an attachment.** The second hard entanglement (`persistence/models.py`, assessment Appendix A row 4) is gone. Ten columns left `conversations` for a new `conversation_strategies` table whose primary key is also its `ON DELETE CASCADE` foreign key: `record_type`, `wdk_strategy_id` (with its unique partial index), `is_saved`, `step_count`, `strategy_ast`, `estimated_size`, `gene_set_id`, `gene_set_auto_imported`, `experiment_id` and `imported_saved_strategy_ids`. The thread keeps identity, name, dismissal, fork lineage and its timestamps. The child carries **no** owner column: scoping is the parent's `(user_id, application_id)` pair and `services/conversations/authz.py` did not move, so every query that reaches the side table drives from `conversations` and inherits its predicates. Absent means never built: a thread starts row-less, the first strategy write inserts, and readers take `Conversation.strategy_view`, a frozen `ConversationStrategyView` whose field defaults **are** the absent-row semantics, so no call site grew a `None` branch. The relationship is `lazy="raise"` with one explicit `selectinload` in the repository reads that need it (plus `populate_existing`, because the side row is written by Core statements that do not synchronize a loaded relationship - the `expire_all()` that `apply_operation` used to need is deleted and pinned by a test instead); the consumers listing does not load it, because its caller reads names. Two pieces of debt died on the way: `ConversationUpdate.strategy_ast_set` existed only to write SQL `NULL` into a `NOT NULL` column (SQLAlchemy's `none_as_null=False` turned it into a JSON `null`), replaced by `ConversationRepository.clear_strategy`, which updates in place so a never-built thread stays row-less and a cleared graph keeps its gene-set and experiment links; and alembic `2026_08_21_0002` normalizes those stored `null`s to `{}` while moving only the rows that actually hold strategy state. Both directions of the migration are tested against a real database. Verified: ruff/mypy/pyright zero findings, import-linter 6/6 kept, 2317 unit + 369 integration tests, `packages/spec/openapi.json` structurally unchanged (the HTTP contract does not move in this batch). Recorded as [a conversation is a thread; its strategy is an attachment](decisions/conversation-thread-and-strategy-split.md), which names the rejected shape: one table with nullable strategy columns, which would still hand a second assistant's threads two foreign keys into PathFinder's science tables.

* **WS2 batch A: the turn state and the wire vocabulary are seamed.** The first two seams of the platform program (`docs/superpowers/specs/2026-08-21-ws2-in-repo-seams.md`) landed together. `PipelineState` is now `TurnState` (the generic turn: message, accounting, approvals, consults, memories) plus one `domain: StrategyDomainState` field holding the eight strategy fields; `Context`/`AgentDeps` split the same way into `TurnContext`/`AssistantDeps` plus product subclasses; the checkpoint serializer keeps a core allowlist and takes product registrations at import, and a guarded migration flushes old-shape checkpoints while sparing the checkpointer's own DDL ledger. The strict round-trip tests caught three REAL pre-existing decode bugs on the way: `ToolApprovalResponded`, `UserQuestionAnswer` and `StepPushFailure` reached checkpoints unregistered, so a strict decode returned plain dicts and attribute reads would have raised. Two dead fields died instead of crossing the seam (`AssistantDeps.writer`, `PendingApproval.plan_id`). On the wire side, the closed `data-*` union became a `StreamPartRegistry` (core parts in core, strategy parts registered by a product module, schema-only tier for payload models no kind emits), the TS `DataPartKind` opened to `KnownDataPartKind | (string & {})`, and the renderer map is a compile-time-total merge of a core half and a strategy half; part kinds keep their names (decision (`assistant-platform: docs/knowledge/decisions/part-kinds-keep-their-names.md`)) because a rename would invalidate persisted event replay. Verified on the combined tree: ruff/mypy/pyright zero findings, 2308 unit + 348 integration backend tests, 2177 vitest, boundaries clean, knowledge gate clean, and a live devtools turn against plasmodb through the new checkpoint shape (frame, build, verify, zero failures). Known couplings deliberately left for batch C: `PendingApproval.phase` still speaks `PhaseRole`, and `turn_state.py` imports `ai/agents/roles` for it.

* **The suite reached 120 passed / 10 failed / 0 flaky, and the feature project is fully green.** Every strategy-edit spec, both purge specs and the enrichment panels pass; the trajectory across the campaign is 94, 105, 120 of 133. The last GO-spec failures were their own lesson: the spec's follow-up question named the mock's GO marker phrase, which routed a plain question into a rebuild that re-minted every step id (the AST leaf changed from `step_65fae9c7` to `step_8b4f3fc6` across one turn) - the question now avoids marker phrases, the precondition reads the vocabulary half through `values`, and the file passes in 33 s. The ten that remain are deep in composite flows and are a healthier class of red: two cross-feature flows now live long enough to fail their axe checkpoint with serious/critical accessibility violations, five journeys share one `rail-strategy-panel` wait, and three are tail-of-run environment flakes; all filed with next steps in the e2e residual-failures backlog item, since closed. One operational lesson is recorded beside them: a worker chat turn on the portal built the portal's semantic index in-process for 2 h 39 m at 785% CPU, freezing every queued turn - the portal's catalog varies per fetch, so a whole-file cache cannot validate, which the per-entry cache entry of the same day closes.

* **The mock now speaks the FRAME contract: discovery before binding, and one half of a GO criterion.** The run-12 edit-family failures reproduced deterministically in the chat debugger: `set_criterion` is enum-guarded to the discovered search universe, the mock never called a discovery tool, and the guard's cold start admitted the first sheet read and then locked the universe to that one search - the second criterion was refused verbatim, `search_name='GenesByTaxon' is not a known value for set_criterion. Choose one of: GenesByText`, three identical replays, retry cap, "Response failed". Separately the GO arc died on the parameter rule `go_term and go_typeahead on GenesByGoTerm are ORed halves of one criterion ... Put the criterion in go_typeahead`, because the canned values filled both. `frame_call` now emits `list_searches` before any criterion so every canned name enters the universe, and `_go_kinases` carries `go_typeahead` only. Both arcs re-run clean end to end against live plasmodb in the debugger: the interpro turn ends on the feedback prose the specs wait for and the GO turn on the success digest, zero tool failures. Six new mock unit tests pin the sequence and the halves rule; the SSE golden is untouched because its prompt rides the echo arc.

* **A transient database ping can no longer latch the API unready forever.** Both health endpoints re-verify the database with a live ping and marked it failed on any exception - and nothing ever marked it ready again, so one blip during a CPU-saturated embedding sweep left `/health/ready` at 503 (with `error: ""`, because `str(TimeoutError())` is empty) while login, writes and enrichment all served correctly; the container reads unhealthy, `web` refuses to start behind it, and every page load sits at "Starting up...". The successful ping now marks the database ready again - the live ping is the authority in both directions - and a failure records `str(e) or type(e).__name__` so the state always names a cause. Three integration tests pin recovery on both endpoints and the non-empty label.

* **The embedding cache keys content, not fetch order, and lives in a volume.** `_catalog_hash` serialized entries in catalog iteration order, and that order differs between a live fetch and a disk-restored catalog, so an identical catalog re-embedded from scratch on most boots - measured as a 4.5-minute rebuild of a 3-hour-old amoebadb index, roughly 20-25 minutes per recreate for all sites, and hours when the portal missed. `build()` now sorts entries by `(record_type, search_name)` before hashing, which also guarantees the cached rows align to the entries by construction; two unit tests pin cache survival across a reordered catalog. The cache directory is a named `embeddings_cache` volume shared by api and worker, so one process's sweep warms the other and a recreate starts warm. The e2e overlay also pins `VEUPATHDB_SITES_CONFIG` to `e2e-sites.yaml` - the portal plus the five component sites the suite drives - so an e2e boot never embeds the seven catalogs no spec touches.

* **The enrichment cluster is explained: the call is legitimately slow, and the specs now say so.** A timed probe of `POST /api/v1/gene-sets/{id}/enrich` with all five types on live plasmodb answered 200 in 163 s with real terms (GO 17/20/20, word 4; pathway reported "Analysis unavailable" for the two-gene set, which is WDK's own verdict). The pipeline is bounded server-side - a 300 s analysis poll cap, capped retries, a process-wide batch semaphore - and the run-12 traces show the request simply outliving the specs' 120 s wait (status -1, neither result nor error), where before the proxyTimeout fix the 30 s rewrite cap answered with a bare 500 that the specs accepted as an outcome. The enrichment helper's ceiling is now 360 s and it extends only its own test's budget via `test.setTimeout`; `ChatPage.goto` tolerates a lagging readiness gate for 60 s. The purge specs were reconciled to the registered-account model in the same pass: the shared WDK account carries strategies the run did not create, so both specs now assert identity, not count - `:66` imports the account's strategies first and proves a dismissed projection is not resurrected, `:120` collects the run's own `wdkStrategyId`s and proves none survives on any site.

## 2026-08-20

* **The suite reached 105 passed / 23 failed / 2 flaky / 0 did-not-run, and the 23 have three measured causes.** The run-10 deletion, durable-SSE and auth clusters are green. Of what remains, (a) the strategy-EDIT family and the edit-ending journeys time out on `/returned 0|root size is 0|too narrow|loosen/i`, the OLD mock's verification-feedback wording, which the rewritten mock never emits - the one reconciled spec (`insert-saved:15`, via `expectVerificationFeedback()`) passes, the rest carry inline copies of the dead regex; (b) the purge specs fail against the polluted shared WDK account, named outright by the flaky `user-data:66`: "sync-wdk re-imported 50 active strategies on plasmodb after dismiss purge" - prior runs left hundreds of strategies under the registered test account, so "everything deleted" cannot hold; (c) the enrichment cluster (analysis, workbench panels, all three cross-feature specs, five site journeys) waits 120 s for a result OR an error and sees neither, which predates every change this week and is the one unexplained cause. All three, with the fix each needs, are in the e2e residual-failures backlog item, since closed.

* **The mock model is site-aware, and two more response-path bugs are fixed.** The deterministic mock (`ai/models/mock_specs.py`, `mock.py`) now derives the organism from the conversation's site (five sites), builds four spec shapes (single, GO, a 3-node InterPro chain, a 5-node combine), and routes prompts naming InterPro/PF00069/EC 2.7 through a feedback arc whose fix-prompt succeeds - which exposed a real harness bug: the frame stage counted tool calls instead of resolved parameters, so a `ModelRetry` read as success and produced an empty build. Specs stop hardcoding node ids through new AST fixtures (`e2e/fixtures/ast.ts`). On the product side, `DELETE /api/v1/conversations/{id}` and restore committed after the response like `/open` did (commit moved before it, three integration tests reading through a second session), and Next's rewrite proxy answered any API call over its 30 s default with a bare 500 - a long multi-site purge among them - so `next.config.ts` sets `experimental.proxyTimeout: 300_000`, recorded with the alternative it rejected in [the API rewrite carries a long call](decisions/the-api-rewrite-carries-a-long-call.md). The e2e cleanup client sent no CSRF header (every non-GET postcondition 403'd silently; header applied at all seven call sites), and `auth.spec.ts` inherited the worker's cookies through `browser.newContext()`, so its signed-out cases ran signed in - it now passes an explicitly empty storage state.

* **Two bugs only a fast client could see, found by running the e2e suite against the production web image, both fixed.** First: `POST /api/v1/conversations/open` returned the new conversation id before the row was committed, because the request-scoped session commits in yield-dependency teardown and FastAPI runs that after the response is sent; the dev-mode web client was slow enough to lose that race every time, and the production build's instant sidebar refresh won it - a trace shows open returning one id and the immediately refreshed listing (HTTP 200) holding only other ids. The route now commits before returning. In-process test transports buffer the whole app call including teardown, so no integration test can reproduce the race; the e2e suite is the regression test. Second: the app's on-load `POST /api/v1/veupathdb/auth/refresh` re-minted `pathfinder-auth` from the `Authorization` cookie even when a valid internal session existed, silently switching accounts - in e2e every worker collapsed onto the one registered VEuPathDB user while older cookie snapshots kept writing as per-worker users (two requests from one test carried different `pathfinder-auth` cookies). The endpoint now honors its own docstring: a request with a valid internal token keeps it (200, no Set-Cookie); absent or expired still mints, pinned by three unit tests. The e2e stack itself was corrected on the way: the web service runs the production image (the containerized dev server was OOM-killed twice and hydrated slower than Playwright clicks), and `docker-compose.e2e.yml` now points at `pathfinder_test` instead of the dev database, into which earlier runs had written several hundred conversations. Full-suite result after all fixes: 94 passed / 26 failed / 1 flaky in 1.3 h with every one of the 254 worker turns succeeding; the residual failures are recorded as four clusters in the e2e residual-failures backlog item, since closed.

## 2026-08-19

* **Every owned resource now belongs to a user under one application, and the same user reaching it from another application is refused exactly as a stranger is.** `application_id` (`NOT NULL DEFAULT 'pathfinder'`) joins `conversations`, `gene_sets`, `control_sets`, `experiments`, `memory_tombstones` and `monthly_usage`; the rest of the tables hang off a conversation and are scoped through it. The value comes from `application_id_ctx`, which the request resolver already set from `X-PathFinder-Service-Token` and which a worker job now sets from the conversation row - the only durable record of which application a turn belongs to - through `attach_conversation_application`, which raises rather than guessing when the row is gone. The check went **inside** the helpers that already decide ownership, so no route grew a parallel check: `owned_by_caller` in `services/conversations/authz.py` (used by the 403 helper, the 404 helper, revert, fork and WDK open), the repository list queries, `GeneSetStore.aget` and `ExperimentStore.aget` plus their cache merges (a process-local cache hit was the one path that could cross applications without touching the database), `ControlSetService` (a public control set is public to its own application, not to every application), and the durable-task queries, which now join the conversation. Memories moved with them: the namespace is `("app", <application>, "user", <user>, <kind>)` from one builder, and the alembic revision rewrites every existing `store` and `store_vectors` prefix to `app.pathfinder.user....` by copying under the new prefix before deleting the old, because `store_vectors` references `store(prefix, key)` with no `ON UPDATE` action; the rewrite is guarded by `to_regclass`, since the store tables are created by the memory lifespan and not by alembic. Quota splits attribution from the cap: `accumulate` writes the calling application's row on a `(user, application, period)` unique key, `get_current` sums every application of the user, so `GET /api/v1/me/quota` keeps its shape and a second assistant cannot double a budget. **Twenty-nine tests pin it**: the authorization matrix gained a third client - the same user, a different application - which found **21 mutating routes** serving another application's request (chat opened an SSE stream, PATCH and fork answered 200, delete answered 204, the memory PATCH and DELETE answered 200 and 204) and now finds none; six HTTP cases on the read half (conversation, gene set, experiment, control set and memory listings, and a single-resource read whose refusal must equal the refusal a stranger gets, not a status of its own); one on the purge; three on memory isolation including a tombstone; three on quota; two on the worker reading the application from the row; and six on the migration, run against real databases - a seeded old-namespace memory moves with its expiry and its vector and comes back on downgrade, the column is `NOT NULL DEFAULT 'pathfinder'` on all six tables, the four new indexes and two unique keys exist, and a database that has never opened the store upgrades without error. The two worker-boundary unit suites now also assert the job runs as the conversation's application. `DELETE /api/v1/user/data` follows the same rule: it dismisses or deletes only the calling application's conversations, gene sets, experiments and control sets, and evicts only that application's entries from the gene-set cache, because a caller that cannot read a resource must not be able to destroy it; an erase-everything action that names no application does not exist yet. Its `deleteWdk=true` arm was deleting **every** strategy in the user's VEuPathDB account for the site - website work included - because it purged what `list_strategies()` returned; it now deletes the ids the already-scoped conversations carry in `wdk_strategy_id`, intersected with what WDK still holds, and leaves a saved strategy a chat only imported alone, since nothing records whether the user made it here or on the website. Recorded as [a resource is owned by a user under one application](decisions/application-id-tenancy.md), which names the rejected shapes: one user row per application (it splits the VEuPathDB identity that `users.external_id` holds, so one researcher becomes several users with several WDK guest tokens and no single budget) and one database per application (a pool, a migration run and a backup per assistant, with no shared quota). Left per user on purpose: `exports`, a short-lived download artifact fetched by a UUID its owner was just handed, which nothing lists.

* **A VEuPathDB bearer token now authenticates, a service token names the calling application, and a bearer request is exempt from the cookie-CSRF header.** Every request resolves to one `Principal` (`platform/principal.py`: `user_id`, `application_id`, `credential`) through one function (`platform/security.py::_identify`), in a fixed order: an `Authorization: Bearer` value that verifies as a PathFinder HS256 JWT is `pathfinder-bearer`, the same header otherwise is read as a VEuPathDB token, the `pathfinder-auth` cookie is `pathfinder-cookie`, and nothing else is 401. `CurrentUser` still hands routes a UUID, derived from the principal, so no route changed. The VEuPathDB path is validated locally, not by asking WDK: the signing key is `GET <VEUPATHDB_OAUTH_URL>/jwks` (default `https://auth.veupathdb.org`), the first entry whose `kty` is `EC`, cached in-process for 120 seconds, and the token is an **ES512** JWT on **P-521** - the same protocol `OAuthClient.getValidatedEcdsaSignedToken` implements for every VEuPathDB container service. Issuer and audience are deliberately unchecked, matching the reference client, whose `validateClaims` is an empty TODO: a site mints tokens for its own client id, so an `aud` check would refuse every browser-session token. A live registered-user token proves two facts the design turns on - its header is `{"alg":"ES512"}` with **no `kid`**, so a key lookup by key id finds nothing, and its payload carries `sub`, `is_guest`, `iss`, `aud`, `azp`, `iat`, `auth_time`, `exp`, `jti`, `preferred_username`, `signature` and **no `email`**. Because `users.external_id` is the email, the bearer path still maps through the resolver the refresh route uses (WDK `GET /users/current`), so bearer and cookie land on one row rather than two; the mapping is remembered per token hash for five minutes. A guest token is 401 on the bearer path, since a guest is a new identity per request and owns nothing durable. A JWKS that cannot be read - unreachable, non-200, or carrying no EC key - is **503** naming the identity provider rather than 401, because the credential was never examined; a token that fails against a key we did hold stays 401. Application identity is the optional `X-PathFinder-Service-Token` header matched in constant time against `PATHFINDER_SERVICE_TOKENS` (`app_id:secret[,...]`, secrets at least 32 characters, parsed at settings load, absent from every repr); an unknown token is 401, an absent one leaves `pathfinder`, and the id also rides a request ContextVar for the tenancy work. `X-Requested-With` is now required of cookie requests only, because a browser never attaches an `Authorization` header by itself. OpenAPI declares all three schemes (`APIKeyCookie`, `HTTPBearer`, `APIKeyHeader`), which fell out of using FastAPI's own security classes rather than patching the schema. **Fifty-two tests pin it**: nine on the validator against a locally generated P-521 pair (expired, wrong key, HS256, missing `sub`, a JWKS with no EC key, an unreachable server, and one fetch for many tokens), twenty-one on the principal, the service-token registry and the resolver (credential order, repeated application id, short secret, missing separator, secret absent from the repr, both ContextVars published), six on the CSRF rule, six on the settings, and ten HTTP integration cases (a bearer GET with no cookie and no CSRF header, a bearer POST that creates a conversation, a cookie POST that is still 403, a guest token, an unknown service token, a PathFinder bearer that never touches the OAuth server, and one WDK lookup across two requests). Recorded as [a VEuPathDB bearer token is the user; a service token is the application](decisions/bearer-identity-and-service-tokens.md), which names the rejected `proxied-user-id`: it is honoured only beside an admin token, and PathFinder acts on WDK **as** the user, so it needs the user's own token rather than permission to name them.

* **Done and removed: a queued or silent turn now keeps its SSE stream open and says "Queued".** `iter_sse` (`ai/conversation/event_stream.py`) wraps its pull from the LISTEN tail in a pending task, so a timeout emits `: keep-alive\n\n` and the tail keeps its asyncpg connection: one comment frame per `SSE_KEEPALIVE_SECONDS` (new setting, default 15, `ge=1`) of silence, on `POST /api/v1/chat` and on the resume stream `GET /api/v1/conversations/{id}/events` alike. A comment frame carries no `id:` and no `data:`, so the durable log, the cursor the client stores at `[DONE]`, and the AI SDK's parser see nothing: `eventsource-parser` 3.0.6 returns from `parseLine` on a leading `:` and only calls `onComment`, which `DurableChatTransport` does not pass, and its `dispatchEvent` fires only when the data buffer is non-empty. Before this the response wrote nothing at all until the worker's first chunk, and a tab that waited behind another turn of the same conversation showed "Response failed - Failed to fetch" while the turn ran to completion server-side. The wait itself is now named: `dispatcher.dispatch` persists `data-turn-status {label: "Queued"}` through the same writer as the user message, before `defer_async`, so the chunk can never land after the worker's `start`; the running message reads "Queued" until `run_turn` writes `start` and `Preparing context`, which is its first pair of chunks, so no second "Running" status exists. The queued chunk carries the turn id the job runs under, so a stop pressed while the turn is still queued reaches the turn the worker polls. Deliberately not added: a queue position, which needs a procrastinate query per request. Pinned by five unit cases on the frame and the setting, two integration cases (the queued chunk is the only row after the user message while the job waits, and the finished turn replays it in the snapshot), three vitest cases on the transport (comments dropped, an all-comment stream survives, a malformed data frame still kills the stream), seven on the placeholder label, and the SSE golden fixture, which gains exactly one chunk at its head. A keep-alive also holds open a stream that nothing will ever finish, so `jobs/maintenance.py::release_stalled_jobs` reads the `ChatTurnPayload` of each stalled `chat_turn:run` job and writes `error` + `finish` + `done` through `ChatEventWriter` before it fails the job, while the conversation lock still blocks a successor turn, and only when the newest chat chunk is not already `done` so a turn that ended is never reopened. A stalled `durable:*` job is released and not closed, so a tool resume whose worker died still leaves its stream open. Pinned by two integration cases and by `cancel_active_turn`, which now has one of its own showing a stop while queued reaching the worker's turn id and not the user message id.

* **Done and removed: every workbench experiment stream POSTed without the header the CSRF middleware demands.** `lib/sse/typedEventStream.ts` hand-built its own request headers, so the five stream callers - Evaluate, Batch and Benchmark in `features/workbench/api/streaming.ts`, the seed stream in `lib/api/experiments.ts` and the threshold sweep in `lib/api/analysis.ts` - sent `accept` and `content-type` and nothing else, and `POST /api/v1/experiments` answered `403 {"detail":"Missing required X-Requested-With header"}` while the browser showed "stream failed: 403". The helper now builds every header through `getAuthHeaders` in `lib/api/http.ts`, the builder the rest of the app already used, so `X-Requested-With: XMLHttpRequest` rides on every stream request; the per-caller copy in `useTaskEventStream.ts` is gone, and with it the `headers` option no caller passes any more. A refused stream now names the API's own `detail` beside the status instead of the bare number. Six vitest cases pin it: the helper on a POST and on a GET, the thrown message on a 403, and the three workbench generators driven through the real helper against a stubbed fetch.

* **A tool the user refuses now reads "Denied" on its sub-agent step card, not "failed".** `SubAgentStepPayload.state` carries `denied` beside `started`, `completed` and `failed`; `ai/lead/sub_agent_stream.py` emits it for a `ToolReturnPart` whose outcome is `denied` and keeps `failed` for a retry prompt or a returned error directive; the card maps it to the AI SDK's `output-denied` state, which the shared tool header already labels "Denied" and which shows the denial message as the result rather than as an error. A refused `delete_step` was indistinguishable from a WDK 404 in the UI and in telemetry before this.

* **The live WDK suites act as a registered VEuPathDB user now, or they skip under their own names.** VEuPathDB serves the WDK service to registered users only, so a cookie-less live suite proves nothing. One session fixture (`tests/conftest.py::wdk_registered_token`, over `tests/_support/wdk_credentials.py`) logs in once with `WDK_TEST_EMAIL`/`WDK_TEST_PASSWORD` through the same `password_login` the login route calls, and `require_wdk_creds` hands that token to a test or skips it with "live WDK now requires a registered user; set WDK_TEST_EMAIL/WDK_TEST_PASSWORD"; five copies of the login helper and six copies of the credential gate are gone with it. The strategy suites put the token on `veupathdb_auth_token_ctx`, which is where the discovery tests move too, because they were calling WDK with no credential at all. In the authz matrix the five owner cases WDK answers - experiment enrich, re-evaluate and results/record, gene-set enrich and results/record - are one parametrized case each and send the token as `X-VEUPATHDB-AUTH`, the header the request resolver reads; without credentials each of the five skips under its own route name, and the non-owner and cross-application refusals still run, because they are refused before anything reaches WDK. With the credentials the matrix is 17 passed; without them, 12 passed and 5 skipped.

* **Done and removed: a caller that supplied every visible required value was refused for a hidden one it could not see.** `validate_parameters` reads WDK's verdict before the local checks, and WDK judges the parameter shape the contextual metadata read hands it, so a hidden parameter missing from that read comes back as "Cannot be empty.". `context_for_metadata_read` was supplying only the hidden parameters that **allow** empty; it now supplies every unset hidden parameter that publishes an `initialDisplayValue`. Measured on live plasmodb.org, `transcript/GenesByText` with the three visible required values set (`text_expression=kinase`, `text_fields=[product]`, `text_search_organism=[Plasmodium falciparum 3D7]`) answered `text_fields: At least one parameter that 'text_fields' depends on is invalid or missing. Errors: { document_type => Cannot be empty. }; document_type: Cannot be empty.` and now returns canonical values including `document_type = "gene"`, disclosed in `substituted` because the caller never stated it. The run path is unchanged: `fill_hidden_required_defaults` still decides what a hidden required parameter is worth when the search is executed, and this is the metadata read. `profile_pattern` travels in that read too, at the published `hsap=1T`, which is exactly the request already measured at 200 when both structural maps accompany it. Pinned by the three unit cases in `test_search_params_under_context.py` that the old rule owned, rewritten to the new one, and by the live pipeline test that named the contradiction. Found by running the live parameter suites with the registered token for the first time; 45 pass, 0 fail.

* **Done and removed: every WDK-backed feature now requires a registered VEuPathDB login, and PathFinder mints no guest identity at all.** VEuPathDB refuses unregistered programmatic access: measured on 2026-08-19 against plasmodb.org and toxodb.org, `GET /record-types/transcript/searches/GenesByTaxon` answers `401 "Valid API Key required for this endpoint."` with no cookie and `403 "This endpoint is only available to registered users, and requires an API key."` with a freshly minted guest cookie, `POST /users/current/steps` answers 403 the same way, and a registered token answers 200; a browser `User-Agent` and `Referer` change nothing. The refusal is one code: `ErrorCode.WDK_LOGIN_REQUIRED`, 401 problem+json, title "VEuPathDB login required", detail "Sign in to VEuPathDB to use searches, strategies and gene sets.", which the web app keys on. The gate is one route dependency, `transport/http/deps.py::require_registered_wdk_identity`, which verifies the request's token locally against the OAuth server's cached ES512 key rather than decoding claims unverified, so a forged, expired or guest token is the same refusal on the cookie path as on the bearer path, and an unreadable JWKS stays 503 naming the identity provider. It is on the 31 routes that reach a WDK account and on no others: `POST /api/v1/chat`, the seven conversation subroutes that act on WDK (step-counts, operations, open, sync-wdk, save-substrategy, insert-saved, fork), the eval pair, the seven gene-set routes that materialize or read a WDK dataset, and the fourteen experiment routes that run, refine, read or delete a WDK strategy. A listing that reads local rows is not gated, so a user with no VEuPathDB session can still list and delete their own gene sets, read and annotate their own experiments, purge their own data, and keep every conversation, note, memory and setting. `tests/unit/transport/test_wdk_gate_route_table.py` names every gated route and carries the reason for each ungated route that can still reach WDK, so a route cannot change category quietly. Guest minting is deleted rather than disabled: `mint_guest_token`, `extract_any_auth_cookie`, `ensure_wdk_identity`, the `users.wdk_guest_token` column (alembic `2026_08_19_0002`, upgrade and downgrade both pinned against a real database) and its repository setter are gone, with the autouse test fixture that kept minting inert. The service account is confined by the transport, not by convention: `_http.py::_effective_token` refuses any `/users/` path when `veupathdb_auth_token_ctx` is empty, before the request leaves the process. `/users/current` is included: it resolves which WDK account the caller is, and without a token the answer is the service account or a fresh guest. `fetch_wdk_user` returns None without a request token, so `GET /api/v1/veupathdb/auth/status` can no longer report the application's own account as the signed-in user, and `DELETE /api/v1/user/data?deleteWdk=true` skips the WDK half and reports `wdkStrategies: 0` instead of refusing the whole purge. The suites take `WDK_TEST_TOKEN` in preference to `WDK_TEST_EMAIL`/`WDK_TEST_PASSWORD`, and a suite about what a route does past the gate says so through one fixture (`signed_in_to_veupathdb`) rather than carrying a token it does not need. **Twenty-five new tests pin it**: six on the service (no token, guest token, unverifiable token, registered token returned, an unreadable key that stays 503, and no request token reading no WDK user), five on the transport guard (a step read and a step create refused with nothing on the wire, the user's own token served, a search listing served as the application, `/users/current` served), seven HTTP cases against a real ES512 key and a stubbed JWKS (chat, a gene-set route, an experiment route and a strategy operation refused with the exact code, title and detail; a guest token and a forged token refused; a registered token reaching the handler's own 404), two on the migration, one that a signed-out purge still deletes the local rows, one that the `Authorization` cookie is read like the header, and three that pin the route table. Recorded as [a WDK-backed feature requires a registered VEuPathDB login](decisions/wdk-requires-registered-login.md), which names the rejected shape: one shared guest or service identity for anonymous users, which would land every user's strategies in one VEuPathDB account where each could read, edit and delete the others' work, and where the researcher would never find the work again under their own login.

* **The web app asks for a VEuPathDB login before any WDK-backed action, and never runs as a silent guest.** One recogniser reads the refusal the API now sends ([a WDK-backed feature requires a registered VEuPathDB login](decisions/wdk-requires-registered-login.md)): `wdkLoginRequiredDetail` in `lib/api/errors.ts` parses a 401 whose problem+json carries `code: "WDK_LOGIN_REQUIRED"` and returns the server's own detail, from an `APIError` (every JSON path, including the Kubb client) and from the plain `Error` the AI SDK's `HttpChatTransport` throws with the response body as its message. `state/useAuthGateStore.ts` owns the prompt: `handleWdkLoginRequired` reports the detail through `toast.error` under one fixed toast id, so a burst of refused queries replaces one toast instead of stacking, and opens the sign-in modal with that same text; it is the one routing call in the query-cache handler, in the composer's `beginStrategy` catch and in `useChat`'s `onError`, so no refusal is retried silently and none is swallowed. The query client used to drop every 401 without a word; it now forwards this one, with the error itself on the notice so the app layer can route it. The composer is the standing gate: `useVeupathdbSignedIn` is true only when the auth status says so, and while it is false the input and Send are disabled, the placeholder and an inline `VeupathdbSignInRequired` banner read "Sign in to VEuPathDB to build strategies", and its Sign in button opens the modal. `?embedded=true` no longer skips the check - `requiresFullScreenSignIn` blocks only a standalone session with the forced modal, and an embedded one renders so the composer carries the prompt in place, which is also why the modal is now reachable in embedded mode and closable when the user opened it. Both shells hold one prompt and one handler: `app/components/VeupathdbSignInGate.tsx` registers the query error handler and renders either the forced modal or the requested one, and the conversation layout and the workbench layout each render it, so a refusal on a gene-set or experiment query opens the prompt on whichever shell the user is standing in. It replaced two copies that had drifted: the conversation layout's second `LoginModal` was dead (its `open` could only be false after the early return), and the workbench layout drove its modal from `signedIn` alone and registered no handler at all, so a refusal there was silent. No UI copy or affordance promised guest use, so none was removed. The Playwright suite acts as the registered account: the per-worker storage state adds `WDK_TEST_TOKEN` as the `Authorization` cookie the API forwards to WDK, the postcondition client in `e2e/fixtures/api-client.ts` takes the browser's whole storage state rather than copying one cookie name (it was dropping that token, which would have 401'd every postcondition call on a WDK-backed route), PathFinder identity stays per worker through `/dev/login?user_id=worker-{N}`, `wdkTestToken()` fails loudly and never prints the value, and the unreferenced `e2e/fixtures/auth.setup.ts` is gone. Pinned by 41 vitest cases over nine files (the recogniser on both error shapes, the store and its routing including a real 401 problem+json driven through `requestJson` and the shared toast id, the query-cache forward against the still-silent 401, the shared gate opening on a refused query and staying shut on an unrelated one, `useChat`'s `onError` driven by a stubbed chat POST, the composer disabled and prompted when signed out and clean when signed in, and the embedded-versus-standalone gate) and three Playwright cases in `e2e/feature/auth.spec.ts`.

## 2026-08-18

* **A non-finite enrichment value is `None`, never 0.0, and the wire says how many pasted genes the statistic used.** WDK returns `"Infinity"` for an odds ratio (and can for a fold enrichment) when the term's genes are all inside the set, and the old `SafeFiniteFloat` clamped every non-finite ratio and probability to 0.0: the strongest hits sorted last and a non-computable FDR read as maximally significant. `EnrichmentTerm` ratios and probabilities are now `float | None` through one annotated type (`platform/pydantic_base.py::NonFiniteToNone`), the ranking rule lives in `services/enrichment/ranking.py` (a `None` ratio sorts first descending, a `None` probability sorts last ascending and is never significant), CSV/TSV write `Inf` for an unbounded ratio and an empty cell for a probability, JSON writes `null`, the HTML report cannot raise, and the analysis table, dot plot and custom-enrichment section render `Inf` / `n/a` from the regenerated nullable types. `custom.py` reports `geneSetInBackground` beside the pasted `geneSetSize`, and its own odds ratio is `None` when a 2x2 cell is zero instead of a clamped finite number (`3600.0`, `180.0`, `880.0` were reported where the truth is unbounded). The authz matrix now covers experiment, gene-set, control-set and memory routes beside conversations (41 cases, five resource kinds), asserts the owner is not refused (401/403/404 or a hang) with a fresh owned resource per case, classifies ids one level into nested bodies including `list[Model] | None`, and proved it can see holes by three injected faults; it found none.

## 2026-08-17

* **Done and removed: an approval-required tool inside a sub-agent now reaches the user, and the answer re-enters that sub-agent.** `optimize_search_parameters`, `delete_step` and `clear_strategy` carry `requires_approval=True`, but a sub-agent run is not streamed through the VercelAI adapter, so its `DeferredToolRequests` output was dropped by an `isinstance` filter: `verify_strategy` raised `TypeError` and `recover_failed_steps` returned an empty `RecoveryDelta` while the real state was "waiting on the user". The suspended run is now kept. The inner call is announced to the client as its own tool part - `tool-input-start`, `tool-input-available` with the real arguments, and `tool-approval-request` whose approval id IS the inner tool call id - so the generic Approve/Deny card renders it with no frontend change; the Lead's dispatch call is deferred with `CallDeferred`, and the whole turn checkpoints on `PendingApproval.sub_agent`, which carries the sub-agent's role, its approvals and its message history. The next turn replays that history with `DeferredToolResults(approvals={...})`, closes the inner part with `tool-output-available` or `tool-output-denied`, and hands the finished delta to the Lead as `DeferredToolResults(calls={dispatch_call_id: delta})` - the value the wrapper would have returned. A second approval defers the turn again instead of running the Lead. Each dispatch is one function (`run_frame`, `run_recovery`, `run_verification`) shared by the direct call and the re-entry, so the spec sync, the build re-sync and the verification digest cannot drift between the two paths, and sub-agent usage is recorded once per half under the dispatch's call id. **Nine tests pin it**, all against the real verification and execution toolsets with scripted models: the three chunks and their ids and arguments, `PendingApproval(phase="verification", sub_agent=...)` with the Lead's dispatch call suppressed, an approval that runs the inner tool exactly once, a denial that finishes the sub-agent with the tool never invoked, a second approval that re-defers, the frame dispatch resumed from its stored arguments, and a strict-msgpack round trip of the nested approval - `PendingApproval` itself was never on the checkpoint allowlist and is now, with the two new models. `sub_agent_tools.py` was 415 meaningful lines against a 400-line gate before this work; the streaming engine moved to `ai/lead/sub_agent_stream.py` and the two spec messages to `ai/lead/dispatch_messages.py`, so every file it touches is under the cap. The turn after a deferral always resolves the dispatch call, because pydantic-ai re-executes a deferred call it is given no result for and the execution role would re-apply its edits: a typed reply resolves the card (approved when the text is nothing but an approval phrase by the injection scanner's own whitelist, otherwise denied with the text delivered to the Lead as the next message), a turn that resolves nothing keeps the card and runs no sub-agent, and two dispatches deferred in one response raise `ConcurrentSubAgentApprovalsError` naming both rather than silently re-running the second. Recorded as [a sub-agent's approval is answered inside that sub-agent](decisions/sub-agent-approvals-re-enter-the-sub-agent.md), which names the two rejected shapes: re-asking through the Lead's `consult_user` (loses the tool's identity and arguments, and re-decides the call instead of resuming it) and dropping `requires_approval` from the sub-agent tools (a ~15 minute sweep and two destructive edits would run unasked).

* **Backlog reshaped by the "stop the bleeding" batch, and one new item that a scripted run proved.** The worker-serialisation item lost its concurrency half: `jobs/worker.py` now runs `WORKER_CONCURRENCY` jobs (default 4; procrastinate 3.8.1 has one global setting, not per-queue), chat-turn and durable-tool jobs are deferred with `lock=<conversation_id>` so only one conversation's jobs serialise, and a `maintenance:release_stalled_jobs` sweep fails any job left in `doing` past `WORKER_STALLED_JOB_TIMEOUT_SECONDS` (default 3600, measured from the job's started event and not the heartbeat, because a starved loop can self-prune a live worker's row) so a killed worker cannot wedge a conversation behind its lock. What remains of that item is the SSE "queued" heartbeat. The heartbeat-starvation item now states that concurrent turns starve the loop more, not less. New, and closed the same day by the entry above: an approval-required tool inside a sub-agent never reaches the user - a scripted `FunctionModel` run shows `optimize_search_parameters` in the verification sub-agent ends in `TypeError`, `delete_step` in the execution sub-agent ends in an empty `RecoveryDelta` with no error, and only the Lead's `consult_user` yields a `tool-approval-request` chunk; the frontend now renders generic Approve/Deny controls for any `approval-requested` tool part, so the fix is entirely on the sub-agent streaming path. Also closed outside the bundle, recorded here so the ledger is complete: `POST /api/v1/chat` and `/api/v1/eval/strategy-gene-ids` now refuse a non-owner (404, hidden existence) with an authz matrix over every conversation-scoped mutating route; the PIGuard pure-approval short-circuit is unconditional (its detection keyed on a chunk nothing emits); `phase_models` is validated against the model catalog; agent telemetry content export is opt-in; custom-enrichment p-values use the exact hypergeometric tail (n=5000, k=200, m=50, x=15 was 2.08e-21 by normal approximation, exact 4.17e-10) and the significance count reads FDR. The wider assessment that ordered this batch is `docs/assessment/2026-08-17-veupathdb-assistant-platform-assessment.md`.

* **Done and removed: the unit tier could reach the network, so an inert stub passed against a live server.** An autouse fixture in `tests/unit/conftest.py` now patches `socket.socket.connect`, `connect_ex`, `socket.getaddrinfo` and the event loop's `create_connection` and `getaddrinfo` for the duration of every unit test, so the tier refuses every connection made through Python's socket module, and a refusal names the test, the target and the two ways out. It derives from `BaseException` rather than `Exception`, which is the difference between a guard and a suggestion: the research clients retry under `except Exception`, and a refusal they could swallow would restore the hazard. No dependency was added - `pytest-socket` is not in the project, and the guard is one fixture and five patched call sites in a file that already exists. The block is total rather than remote-only, because a rule with an exception nobody can see is not a rule. Running the suite under it exposed **zero** inert stubs, which is the honest result and not a null one: the class was found once, fixed once, and is now closed by construction rather than by inspection. What it did expose is that **two files in the unit tier were integration tests** - `test_wdk_identity.py` and `test_saved_strategy_consumers.py`, ten tests that read and write the database - and they have moved to `tests/integration/`, so no production test carries the opt-in marker at all. **2,058 unit tests pass with every socket refused**, ten of them covering the guard, including that `except Exception` cannot swallow it and that `AF_UNIX` is not the network. Two limits are recorded rather than papered over: collection-time downloads happen before the fixture runs, and a C extension holding its own socket is not covered. The [verification-gates convention](conventions/verification-gates.md) carries both, plus `ruff format --check src/`, which does not overlap `ruff check` and was silently drifting on eight files.

* **Four deferred minors from the parameter-resolution and phyletic-contract ledgers, closed.** A `profile_pattern` that states one species code twice was taking the "not a census pattern" wording, which sends the reader to look for a malformed token that is not there; `_read_census` now returns the repeated code beside the states, and the 422 names it and quotes the two ways to state it once. Both paths to the wire raise it: the expansion path and `_normalize_parameters`, which reaches WDK without expanding. The unreadable-tree fallback in the same function re-parsed the pattern it had already parsed, and now encodes the states in hand. WDK-PARAM-008 (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`) anchored at `domain/parameters/values.py:to_wire`, which is not where the substitution comparison lives; it now anchors at `services/catalog/wdk_substitution.py:substituted_params`, and the enforcing test is unchanged. The `_word_weights` docstring in `param_sheet.py` claimed a rare word "must outweigh any number of common words", which the arithmetic does not do: a word `n` labels hold is worth `1/n`, so a unique word is worth 1.0 and three words of weight 0.5 beat it. The comment now states that bound. Left alone and recorded here rather than half-done: `_vocab_signature` in `param_dag.py` is recomputed per call, and memoizing it is not the two-line change it looks like, because `ParameterInfo` is a mutable Pydantic model that is neither hashable nor safe to key by identity, and the dominant cost is `vocabulary()` itself, which three of the same call sites invoke directly.

* **The half of a criterion nobody wrote into is now switched off rather than asked about, and the half that widens the search is refused.** A `radio-params` pair is two required parameters one query ORs, so the intuition that filling both narrows the search is exactly backwards (WDK-SITE-007, `veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`). `set_criterion` reads the pair off the search definition - the same cached read the phyletic derivation uses, so it costs no extra GET - and binds `N/A` into the free-text half of every declared pair. A criterion written into the free text comes back as a retry that names the pair, says the vocabulary half cannot be switched off and quotes its default, lists the vocabulary entries nearest to the value with the wildcards stripped, and sends a wildcard to `get_parameter_options(query=...)` to be expanded into the entries it covers. The off value is reported in `defaulted_params`, so the user is told about a value the request never stated. Measured on plasmodb.org for *P. falciparum* 3D7: `ec_number_pattern=2.7.-.-` beside `ec_wildcard=N/A` returns **364**, and so does the published default `2.7.11.1` beside `2.7.*`, because that wildcard happens to cover the default; `2.7.11.1` beside `N/A` returns **136**, and beside `*protease*` returns **141** - the 133 protein kinases of the default carried into a search asking only for proteases. Two live behaviours this replaces: a turn that bound `ec_wildcard=2.7.*` next to a default it did not choose, and a turn that left it null and got an open slot, because the walk refuses to inherit a free-text default. The FRAME procedure states the same rule, the resolver bench arm records a refused free-text half and continues so the guard is measured, and the rule is `ENFORCED`, which empties the `SILENT` column for the third time: **32 of 83 untested, all of them HARD or CONTRACT.**

* **The search whose criterion nobody could state now states it once.** `GenesByOrthologPattern` carries one criterion - which species must have an ortholog and which must not - in three parameters: two visible free-text lists the query never reads, and a hidden required SQL `LIKE` pattern that is the only one it does read. The model could propose the lists and could not touch the pattern, so the pattern came from `initialDisplayValue`, which is `hsap=1T`, a well-formed expression in a different parameter's grammar on a different site. **The two lists are now the proposal, the pattern is derived from them, and all three are written together.** The sheet gives both lists the clade tree as their vocabulary, so the model names species and clades by code or by label; `derive_phyletic_overrides` resolves them against that tree, pushes each clade down to the species the census holds, sorts the tokens into census order, and returns the pattern beside the two canonical lists for `set_criterion` to bind. An unknown term is a retry naming the nearest labels, a code in both lists is a conflict, and two empty lists are a retry rather than a binding - the bare `%` matches every census, so it reads as a phyletic answer and is not one. Live on plasmodb.org for *P. falciparum* 3D7: the derived `%hsap:N%pfal:Y%` returns **3,347** genes, `%pfal:Y%` returns 5,389, and the published default returns **0**. On the 20 gold strategies, 332 parameters, the propose arm moves from 285 exact / 18 wrong to **288 exact (stated 226, defaulted 62) / 15 wrong**, questions and unset values unchanged at 20 and 9, with the pattern and both lists exact on both gold steps of that search; the one wrong value left there is the organism strain, which is a model choice. One live turn bound the same three values after a single retry that named the nearest labels. Deleted with the work: `_build_phyletic_tree`, `_expand_entries`, the quantifier tokens and `is_census_pattern` from the wire layer, which now reads a value through `_read_census` and refuses a code that states two states; `integrations/veupathdb/phyletic_tree.py:phyletic_tree_of` is the one tree builder and the sheet, the binding and the wire guard all use it. WDK-SITE-005 (`veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`) and `WDK-SITE-006` are `ENFORCED` by backend tests, so the untested count is **33 of 83** and the `SILENT` column is unchanged at one. Recorded as [the two lists are the proposal](decisions/phyletic-lists-are-the-proposal.md). The hidden-required-defaults item keeps only its unmeasured tail: whether the hidden defaults on the other 181 searches return rows.

* **Two findings that work produced on the way, both kept.** First, "display purposes only" is a statement about the query and not about the metadata read: the contextual `POST` for that search answers **500** when the context carries `organism` and `profile_pattern` and omits the two structural maps, and either map alone is still a 500, while both together are a 200 with `validation: {level: SEMANTIC, isValid: true}`. Every hidden parameter that allows empty now goes into a metadata read's context at its published default, by shape rather than by name, at all three read sites. Second, that fix could not land until substitution detection was corrected. When the contextual read fails, the client falls back to the static `GET`, whose echoed values are the published defaults, so every value the caller set differs from the echo and none of those differences is WDK substituting anything (WDK-PARAM-008, `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`). The comparison is now against the canonical values actually sent, a vocabulary echo is compared as a set, a hidden parameter this read supplies is never reported, and `values_were_read` gates both the comparison and the validation verdict when the read fell back.

* **Fixed: `PF00069` was not `PF00069 : Pkinase`, and the retry pointed away from it.** A typeahead vocabulary writes its terms as `<accession> : <label>`, and a proposal of the accession alone was refused as off-vocabulary. The nearest-entry list that came back was ranked by character similarity, so it offered `PF00569 : ZZ` and `PF00169 : PH` and not the one entry the accession identifies; two retries later the model changed `domain_database` to `INTERPRO` and bound `IPR000023 : Phosphofructokinase_dom`, which is the wrong science. Three changes, together: `match_exact_option` accepts a proposal that is the leading accession of exactly one entry, and refuses it when two entries share it; the nearest entries lead with the ones the proposal starts, so `PF0006` answers `PF00069 : Pkinase`; and the sheet pins an entry whose accession appears in the request as a word, not only one whose whole term appears. A shared accession is refused by naming the entries that share it, so the ambiguity is recoverable in the same turn rather than reading as an absent value. An accession holds a digit and is at least four characters, so a leading word such as `Plasmodium` is a label and matches nothing. [The decision](decisions/unmatched-accession-stops-the-chain.md) is amended again.

* **Done and removed: parameter resolution had three proposers and no contract.** There is one now, and it is the model. `set_criterion` with no `params` returns a parameter sheet - every visible parameter with its type, help, default, bounds, dependency and vocabulary - beside a `params_template`, the object to copy and fill, and the next call takes a value or an explicit null for each of them. A second sheet for the same criterion carries the parameters without the vocabularies, which the model already holds. The walk validates and binds: unknown names and off-vocabulary values are did-you-mean retries, numbers and JSON-encoded lists are coerced, a null binds the disclosed default or opens a slot, a dependent whose vocabulary changes under the bound parents comes back to be decided once, and a numeric parameter left null while the criterion states a quantity comes back unread rather than defaulting in silence. Measured on the same 20 gold strategies, 332 parameters: **exact 285 (stated 222, defaulted 63), wrong 18, asked 20, unset 9**, against a floor of **154 exact (all of them defaults), wrong 48, asked 115, unset 15** for the walk with no proposer at all. The four arms recorded before this work - 168/48/101 as the recorded baseline, 184/58/75 for production with the resolvers discarded, 205/62/56 with the resolvers allowed to bind, and the experiment harness at 255/54/14 and 276/27/20 - were measured before a held-back numeric default counted as a question and before the scorer compared wire values by kind, so they are history and not a column beside the new floor. Deleted with the work: both resolver agents and `ai/agents/vocab_resolver.py`, `ValueResolvers`, `bind_inferred`, `Provenance.INFERRED`, `map_intent_to_value` and every rule in it that read English, `narrow_candidates` and `vocab_narrowing.py`, the dead `resolve_search_parameters` and `get_parameter_dependencies` tools with the `DagResolution` half of the walk, and `organism_scope`, `direction` and `param_overrides` from the tool surface. The sheet does **not** embed, which is the one place the design changed under measurement: embedding a 5,461-entry vocabulary takes 238 seconds in the api container, so a shortlist is by word overlap with the goal, with anything the request names verbatim pinned. Recorded as [one proposer, one validator](decisions/one-proposer-one-validator.md); [the 2026-08-10 resolver decision](decisions/the-model-reads-the-request-not-a-cosine-score.md) is amended rather than deleted, because embeddings still may not decide a value - and its evidence section had claimed a profileset "binds correctly" that never bound, which is now struck. [An unmatched accession](decisions/unmatched-accession-stops-the-chain.md) and [a value the request already states](decisions/a-value-in-the-request-is-not-a-question.md) keep their principles and lost their rules; both now name what carries them. The live DeRisi prompt then built end to end, 16 steps, with zero invented parameter names, on the fourth run - the sheet arriving from `set_criterion` itself and the repeat losing its vocabularies are the two changes between that run and the third.

* **Also from the measurement: a search can offer the same criterion twice, and both halves are ORed.** WDK-SITE-007 (`veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`). ApiCommonModel declares the pairs in a `radio-params` property list - `go_typeahead`/`go_term`, `domain_typeahead`/`domain_accession`, `ec_number_pattern`/`ec_wildcard`, `metabolic_pathway_id_with_genes`/`pathway_wildcard` - and the property is published on the wire. The intuition a form gives is that filling both narrows the search; the query unions them. Measured on plasmodb.org for *P. falciparum* 3D7: `GO:0004672` alone returns 105 genes and the same pick beside the wildcard `*kinase*` returns **192**; `PF00069 : Pkinase` alone returns 81 and beside `*kinase*` returns **144**. Both halves are `allowEmptyValue: false`, and two of the published defaults are refused by the search that published them, so there is no off position - only a value that matches nothing. The worst case is `GenesByEcNumber`, whose typeahead half cannot be empty and whose published default is a real EC number: a search asking only for proteases carries 133 protein kinases and nothing in the response says so. The rule says which half is authoritative; the guard that enforces it is the entry above.

## 2026-08-16

* **The resolver bench was scoring the wrong input, and the design turned out to be sensitive to exactly that.** Every gold strategy carries `prompts.precise` - the request a user would type - and the bench loaded it but never used it, because it took the step's listing label whenever there was one. So the whole recorded baseline described resolution on a short phrase rather than on the shape production hands it. Feeding the request instead moves wrong values from **48 to 68** and makes the heuristics assert that the request stated **23** values it never stated about that parameter. More of the user's own words makes them more confident and less correct. First cut taken from that: an identifier in the text was written into every vocabulary-less param of a search, because only a *sibling's vocabulary* counted as a rival home - one `GO:0016301` landed in both a free-text query and a document-type selector, each claiming the request said so. It now binds only where one param can hold it, the rule the numeric slots already follow. **Wrong 68 to 58, exact 173 to 183, no new questions**, and the label baseline is unchanged.

* **Fixed: the published `profile_pattern` default reached the query unexamined.** The census guard returned early unless the value was wrapped in `%`, and WDK's own `initialDisplayValue` for `GenesByOrthologPattern` is `hsap=1T` - unwrapped, and an expression from OrthoMCL's grammar. So the one value most likely to be wrong was the one value nothing checked, and it returns an empty answer with HTTP 200. A pattern that is not built from census tokens is now a 422 naming the two tokens that work.

* **Fixed: a spec could be `ready_to_build` and still not convert.** Readiness reports that every criterion is bound and a structure exists; it does not run the conversion. A nine-criterion turn passed it, then died on `ValueError` after FRAME had spent the expensive part of the turn. The conversion failure is now a retry that names the structure, so the turn survives and the Lead can fix it.

* **A value the search chose is now visible as one.** `defaulted_params` was recorded per criterion and shown to the framing agent, but never reached the Ledger or the browser, so the only account of an assumed value was whatever the reply chose to narrate. The Ledger's criterion card now marks those params as assumed.

## 2026-08-15

* **Fixed: leaving a conversation and returning lost it.** Two independent defects, both found in the browser and both fixed with tests. (1) The transcript query was cached with `gcTime: Infinity`, so the list a mount read was the list every later mount got. A conversation created in this tab reads its transcript before the first turn exists, gets a 404, and caches the resulting empty list forever - so returning from the workbench, or from another chat, showed an empty conversation and only a page reload recovered it. The transcript is now re-read per mount. (2) A running turn was never re-attached, because `resume` was derived from `allowMissing`, which compares the URL id to a UUID the tab generated. Every conversation starts from a locally generated id, so that comparison stays true for the life of the tab and the chat kept treating a real conversation as an uncreated draft: no resume request was issued at all, the composer showed Send while the turn ran, and a reload appeared to fix it only because it minted a new UUID. Resumability is now its own flag - the URL names a conversation - and it is captured at mount, so the draft-to-URL rewrite cannot open a second stream over the live one.

* **Fixed: a durable task finished and the answer never appeared.** A turn that defers to a durable tool ends its own response at the interrupt, by design. The worker then runs the task, resumes the graph, and writes the rest of the turn to the event log - but nothing told the page that was still open to read it, so the user was left with a progress bar at 100% and no conclusion. The whole final message existed in the database the entire time and appeared only after navigating away and back. Three things had to hold at once, and finding the third took two failed attempts that are worth recording. (1) A trigger: the task's own progress stream now announces when the task settles, and the card re-attaches the chat. (2) The announcement cannot depend on the terminal chunk alone - a stream opened while the task ran can end without one, while a stream opened after it finished always gets it on connect, which is why the reload path looked healthy and the live path did not. It now announces when the stream ends, whatever the reason. (3) The re-attach then failed silently, because the event log stores the user's own message so a snapshot can rebuild the transcript, and that row is not an AI SDK chunk. The transport calls `controller.error` on anything its schema rejects, so the replay died on its first row, before the assistant's first token. The transport now drops that row rather than failing on it. The same `controller.error` path explains a `reading 'state'` TypeError seen earlier.

* **Fixed: two Lead tools turned a wrong argument into a dead turn.** Asking for control tests on a combined step made the Lead pass `Combine` - the label the strategy view renders for a combine node - as a variant's `search_name`. WDK rejected it once the run reached the server, so the turn spent itself and reported no metric and no way forward. Both variant tools now refuse a combine step before running anything and name `run_control_tests_on_step`, which takes a step id, instead. Separately, `import_control_ids_from_strategy` and `compare_variants_scored` parsed their id arguments with `UUID()`, so a WDK strategy id - which the conversation shows everywhere - raised `ValueError` and ended the turn with `badly formed hexadecimal UUID string` in the user's face. Both now answer with a retry that names the value they got and the kind of id they want.

* **Fixed: an invalid phyletic state emptied a strategy in silence.** A plain ToxoDB request for kinases with no ortholog in *C. parvum* framed correctly and then wrote `%cpar:0%` into `profile_pattern`. The census tokens are `code:Y` and `code:N`; `:0` matches nothing, WDK answers 200 with a count rather than an error, the ortholog step returned 0 and the whole intersection collapsed to 0. Opening that step in the editor read "0 included, 0 excluded, 864 unconstrained", which is the same symptom the widget used to produce before its encoder was corrected - so the grammar was fixed on the widget side and not on the agent side. The code half of each entry was already validated against the site's vocabulary, and `cpar` is real, so nothing objected. The state half is now validated too and an entry that states neither presence nor absence is a 422 naming the entry and the two tokens that work. This is the hazard `WDK-SITE` was written for, reached from an ordinary prompt rather than from a hand-made pattern.

* **Fixed, both halves: an edit made outside the flow that produced an artefact never reached the artefact.** A parameter changed in the graph editor moved a step from 3,259 to 897 and the root from 15 to 3. Two things then disagreed with reality, and they needed opposite fixes, which is the part worth carrying: **WDK owns the strategy**, so anything stored here is either stamped with when it was true or re-read from the server. (1) The Ledger's Build tab kept showing 3,259 and 15 marked `ok`, and the Lead quoted 15 as current while asserting nothing had changed. The Ledger is a record of what the build did, so it stays frozen and now says its counts are from the build. The reason its staleness check never fired is that `detect_build_staleness` compared the recorded counts against `live_step_counts`, which read the same persisted AST the build wrote - **a cache compared with itself, unable to detect any edit by construction**. The live side now reads WDK, and `live_step_counts` is gone. (2) A gene set went the other way: it stores its member ids and rendered its results by re-reading the step it came from, so the panel showed "15 genes" beside a table of 3, and an enrichment saved against it stopped describing its own input. Membership is what the set stores, so results are now reported from a step materialized from those ids. WDK refuses to run a step belonging to no strategy, so the materialized step is held by an internal one, cached by the membership hash.

* **Verified in the browser, not reproduced: the two open agent items.** A request stating "top 10 percent" bound `min_expression_percentile` to 90 against a declared default of 80, selected the trophozoite sample window, and asked no questions under an explicit use-defaults instruction. Both numeric intent and use-defaults are held open pending their original repro, since this search carries two numeric slots and so does not exercise the single-slot rule that was added for them.

## 2026-08-14

* **A hidden parameter was choosing the science, and the bundle covered none of it. Added `WDK-SITE`, a rule family whose falsifier is ApiCommonModel rather than WDK.** `GenesByOrthologPattern.profile_pattern` is hidden, required, 4000 characters of free text, and it is a **SQL `LIKE` pattern** matched against a colon-joined species census - `%code:Y%` for present, `%code:N%` for absent, `%` being the wildcard rather than a separator. Nothing upstream states that grammar in prose; it was reconstructed from the query's own SQL (`veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`) and confirmed by measurement on plasmodb.org and toxodb.org. Four things follow and none of them is a refusal: a wrong pattern is not refused, tokens out of ascending code order match nothing (`%atum:Y%bant:Y%` returns 387 and the reverse returns 0, on three separate pairs chosen because tree order and code order disagree), a clade code matches nothing, and **WDK's own published default returns nothing** - `initialDisplayValue` is `hsap=1T`, which is a valid expression in OrthoMCL's *different* `phyletic_expression` grammar (it returns 9691 groups there) and is meaningless here. Six `WDK-SITE` rules plus two `WDK-PARAM` rules (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`) for the general lesson: `initialDisplayValue` is whatever the spec holds, the model default behind it is stored by a setter whose javadoc promises validation and whose body does not (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`), and `isVisible: false` is presentation only - a grep of the whole WDK repository finds `Param.isVisible()` read in exactly two places, one of which just publishes it. The new explainer is site-model parameters (`veupathdb-py: docs/knowledge/wdk/model/site-model-parameters.md`); `scripts/check-wdk-rules.mjs` learned the `SITE` namespace and its suite went from 27 tests to 28. ApiCommonModel had been pinned since the bundle was created with a note admitting nothing cited it; that note is now deleted rather than softened.

* **Filed two defects the research found, both PathFinder's rather than WDK's.** The phyletic profile widget writes a pattern that matches nothing is ranked first in the WDK section because the trigger is an ordinary user action: pick species in the step editor, submit a valid form, get zero genes and no error. `encodeProfilePattern` emits `code>=1T` / `code=0T` - OrthoMCL syntax, measured at 0 on both sites - and three separate faults have to be fixed together, since the token grammar, the ordering and the clade-versus-leaf expansion each independently yield zero. Its own test file asserts `pfal>=1T` literally in three places, so **the test pins the defect and has to be rewritten rather than patched around**; `decodeProfilePattern` cannot read the correct form either, so a step built by PathFinder's own backend opens in the editor reading "0 included, 0 excluded". Second, filling a hidden required parameter from `initialDisplayValue` chooses the science: the fill is the right shape - WDK demands these parameters and the model cannot supply them - and the value it fills carries no guarantee at any layer. The same belief is written into `param_dag.py:_is_free_text_query` as a comment, and both have to move together.

* **Review caught the worst of it, and it made the finding worse rather than smaller.** The query is a `UNION`, and its **first** branch never touches `LIKE`: it inspects the pattern *string* with `not like '%:Y%'` and, when the string carries no `:Y`, returns every ortholog-less protein-coding gene for the selected organism. So "a wrong pattern returns zero" was the wrong statement of the hazard. **A wrong pattern returns whatever that branch yields for that organism**, which is zero here and is guaranteed nowhere - and a plausible non-zero count from a meaningless pattern is the worst answer this product can give. Four of the measured forms carry no `:Y` (`hsap=1T`, `hsap>=1T`, `hsap=0T`, prose) and their zeros are a property of the data; the two `:Y`-bearing zeros (`%zzzz:Y%`, `%MAMM:Y%`) are intrinsic. **Every string PathFinder's widget can emit lacks `:Y`**, so it never reaches the matching branch at all. I isolated that branch with `hsap=1T` on **eleven organisms across both sites** and it was empty on all eleven - recorded as a limit of the measurement, not as a refutation. A residue argument that had been offered as reassurance was deleted rather than repaired: it was vacuous, since both patterns it compared lack `:Y` and so both include the same branch. Also from review: `WDK-SITE-001`, `-002`, `-004` and `-005` are **live-only** - `profile_string` is built outside all four pinned repositories - so each now says so in the rule itself, and sources.md (`veupathdb-py: docs/knowledge/wdk/sources.md`) gained the mirror image of its source-only ledger, with a re-run instruction per rule. A rule with no upstream and no re-run is unfalsifiable, which the charter forbids. Vocabulary counts were re-derived with `jq`: 865 terms, 818 lowercase, 47 uppercase, no duplicates, every term four characters except the three-character root `ALL` - so `three_letter_abbrev` is wrong about its own contents for 864 of 865 rows.

* Recounted the rule bundle honestly afterwards. **81 rules, 45 UNENFORCED**, and the number that matters is that the `SILENT` untested column went from **0 to 5**: four of the new site rules and the `initialDisplayValue` rule. The backlog item that claimed the `SILENT` class was closed no longer claims it.

## 2026-08-10

* **Read what WDK already answers, and stop reporting numbers it did not give.** Five changes, all from the pinned rule set rather than from a failing run. (1) One named count: the two count paths returned different quantities, because `estimatedSize` tracks `displayTotalCount` while the fallback read `totalCount`, and only the view pair matches the records returned. (2) The four counts became optional, so an absent count can no longer read as a scientific zero; the response schema and generated types were made honest rather than kept convenient. (3) A negative `estimatedSize` now reads as no count instead of surfacing as a gene count. (4) The validation bundle returned by the search endpoint is read instead of discarded, honouring the rule that a false verdict at level `NONE` means nobody checked. (5) WDK reports which values it substituted, so provenance is now corrected by the server that already knew it. Writing the first rule test also found a live contradiction: the model was told to send the synthetic tree root as a select-all shortcut, and the canonicalizer rejects it, as WDK does. Also closed: the delayed-result sentinel is recognised by shape and retried.

* **Added `docs/knowledge/wdk/`, a falsifiable WDK reference, and a gate that fails when its evidence stops resolving.** Four groups - rules (`veupathdb-py: docs/knowledge/wdk/rules/`), model (`veupathdb-py: docs/knowledge/wdk/model/`), rest (`veupathdb-py: docs/knowledge/wdk/rest/`) and [pathfinder](wdk/pathfinder/) - carrying **73 assertions** about WDK, each with a GitHub link pinned to a 40-character sha and an anchor naming the PathFinder symbol it governs. Most are confirmed live on plasmodb.org and toxodb.org rather than reasoned about; six are source-only and sources.md (`veupathdb-py: docs/knowledge/wdk/sources.md`) lists them by name. The new gate `scripts/check-wdk-rules.mjs` (pre-commit and CI, with its own fixture suite) fails on an unpinned citation, a moved anchor, a named test that no longer exists, and prose citing a withdrawn rule. Every `ENFORCED` and `PARTIAL` status was then audited against one standard - would the named test go red if the rule were broken - which downgraded three: WDK-VOCAB-002 (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`), whose test drove the canonicalizer while its anchor is a second, untested expansion in `integrations/`, and WDK-STRAT-002 and WDK-STRAT-003 (`veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`), whose hypothesis trees came out of `flatten_tree` and so satisfied single-rootedness and reachability by construction. The honest tally is **8 ENFORCED, 9 PARTIAL, 56 UNENFORCED**, and the number that matters is that **19 `SILENT` rules have no test** - the class where WDK answers 200 and the science is wrong. Filed as one item, 56 of the 73 WDK rules have no test, which ranks the conversion `SILENT` first and carries the open questions the research left behind, including a `JSESSIONID` belief that did not reproduce on three live probes.

* **Root-caused the recurring crash, correctly this time, and fixed the seam behind three earlier bugs.** Pushed back on: the same issues kept returning, which was right. Two findings. (1) `No tool invocation found for tool call ID` is thrown by the Vercel AI SDK **client**, not OpenAI, when a `tool-output-error` names a call the client never saw announced -- it never reaches a backend log, which is why it read as a silent provider rejection. [no-openai-item-ids](decisions/no-openai-item-ids.md) misattributed it and now carries a correction; the real one is [chunk suppression follows the call, not a list of chunk types](decisions/suppression-follows-the-call-not-the-chunk-type.md), since fixed and verified in the browser. (2) "Get a search's parameters under a context" had **no owner**: six call sites, four exception types caught, five recoveries, two with no handling at all -- and the two with none are exactly where B16, the default-vocabulary read, and the abandoned criterion landed. One owner now: [a contextualized param view is an enrichment](decisions/contextualizing-params-is-an-enrichment.md). Verified against the live 500: WDK fails, we log once and return all 6 params.

* **The multi-criterion mega prompt, in the browser, on a real account.** No crash, on either the Portal or PlasmoDB -- the turn that used to die on `No tool invocation found for tool call ID` now completes. On PlasmoDB, FRAME operationalized all five criteria (four kinase routes as a UNION, the non-syntenic orthology transform, the trophozoite mass-spec-or-microarray alternative, Broad 3K variation, and phyletic specificity) for $0.03. It then declined to build, because one criterion's search 5xx'd -- correct behaviour, wrong conclusion: the value WDK 500s on the refresh endpoint runs fine (a non-empty result). That 5xx has since been root-caused and fixed at the seam behind it -- see [a contextualized param view is an enrichment](decisions/contextualizing-params-is-an-enrichment.md). Two claims the same run made on the Portal were checked and are Portal artifacts: `GenesBySnps` genuinely does not exist there, while `GenesByOrthologs` does and retrieval simply missed it among 2,356 searches.

* **Done and removed: the dependent-param false rejection.** Two independent defects, both proven on live WDK. The tool was reading a dependent vocabulary under WDK's DEFAULT parents, so the model saw HB3's time points for a criterion bound to 3D7 and correctly reported hours that do not exist in what it was shown ([decision](decisions/a-dependent-vocabulary-is-read-under-its-parents.md)). Separately, a multi-pick answer was serialized to wire form at the tool boundary, so the whole array counted as one option and the model was told its own correct answer was invalid ([decision](decisions/an-override-list-stays-a-list.md)). Same prompt, before and after: 4 `set_criterion` failures to **0**, and the built strategy built (a large result protein-coding, intersected with a large result top-percentile trophozoite and 81 `PF00069` kinases, giving the intended genes). Filed from that run: a numeric bound stated in the request is ignored, then reported as honoured.

* **Fixed: an unmatched accession stops the chain.** "InterPro domain PF00069" bound `IPR000023 : Phosphofructokinase_dom` and returned almost nothing with verification reporting success, because the accession is Pfam and the dependent vocabulary was IPR-only. Live re-run now binds `PF00069 : Pkinase` and the intended genes. See [decisions/unmatched-accession-stops-the-chain.md](decisions/unmatched-accession-stops-the-chain.md).

* **Fixed: numeric defaults were being discarded.** WDK types numeric bounds as `string`, so the free-text guard (which exists to stop `GenesByText` inheriting `*reductase`) swallowed their declared defaults and asked five needless questions on `GenesBySnps`. That criterion now resolves with zero open slots. See [decisions/numeric-default-is-not-an-example.md](decisions/numeric-default-is-not-an-example.md).

* **Fixed: a parent term is a selection.** The organism tree matched only leaves, so a step scoped to "Plasmodium falciparum" (a node with 20 children on live WDK) rendered as "0 of 62 selected", and edits filtered the raw value so unchecking a leaf did nothing. See [decisions/parent-term-is-a-selection.md](decisions/parent-term-is-a-selection.md).

* **Fixed: the strategy structure is a tree.** `set_structure` left-folded a flat list, so `(B UNION C)` on the secondary input was inexpressible; the Lead correctly refused to flatten it. The nested form recovered a gene the flat form lost (3 vs 2). See [decisions/structure-is-a-tree.md](decisions/structure-is-a-tree.md).

* **Root-caused and fixed the tool-call-id crash.** Not orphaned tool pairs (`pair_tool_calls` logged zero corrections); it was `openai_send_reasoning_ids`, which defaults to True for reasoning models and echoes provider item IDs back from a history we rewrite. See [decisions/no-openai-item-ids.md](decisions/no-openai-item-ids.md).

* Real-account browser testing on a multi-criterion reference strategy. Fixed [build_strategy's unactionable retry](decisions/build-retry-must-be-actionable.md). Filed three findings: the tool-call-id crash on complex turns (since root-caused and fixed, see above), FRAME ignoring an explicit defaults instruction, and the organism param rendering as unset (since fixed, see above).

## 2026-08-09

* Done and removed: **FRAME turn cost**. The 40K bar was arithmetically impossible, but investigating it found a real defect: elision made agents re-fetch data they already had (a large share of tool calls in one turn). Fixed by keeping a digest. See [decisions/elision-caused-refetching.md](decisions/elision-caused-refetching.md). **Backlog is empty.**

* Done and removed: **FRAME to BUILD to VERIFY migration**. The flip was already complete in code; what remained was prose describing the deleted architecture to the model, and verification. Proven end to end on live WDK ( 590/598 transcripts, verification passed). Two decisions recorded: [prompts-match-the-architecture](decisions/prompts-match-the-architecture.md) and [strict state + flushed checkpoints](decisions/no-checkpoint-truncation.md) (reversed once the compat shim was pointed out). The live run also exposed a real cost gap, since investigated and fixed: [elision-caused-refetching](decisions/elision-caused-refetching.md).

* Removed as stale: **experiment controls and scoring (Phase 2b)**. Already built, wired, and tested. The real gap was discoverability: the unscored comparison tool never named its scored counterpart, and nothing guarded that either stays registered. See [decisions/capability-must-be-reachable.md](decisions/capability-must-be-reachable.md).

* Done and removed: **test fixtures should not cast to their type**. 32 casts removed, 10 lying fixtures fixed (including one using a raw string where the API returns a typed `ParamValue`), shared factories added. See [decisions/fixtures-are-built-not-cast.md](decisions/fixtures-are-built-not-cast.md).

* Done and removed: **devtool reports handled issues as anomalies**. The `silent_*` detectors now read the reply, and `RunCapture` no longer discards it. See [decisions/silent-anomaly-must-read-the-reply.md](decisions/silent-anomaly-must-read-the-reply.md).

* Closed as won't-do: **restore faker and msw generation**. Reproduced at 586 type errors, traced to a hardcoded `Partial<T>` override shape no plugin option controls, and concluded the output conflicts with the real-data testing rule. See [decisions/no-faker-or-msw-generation.md](decisions/no-faker-or-msw-generation.md). Replaced by the narrower fixtures-should-not-cast item, which is what the drift was actually about and which is now done: [decisions/fixtures-are-built-not-cast.md](decisions/fixtures-are-built-not-cast.md).

* Removed as stale: **JSONValue name collision**. `JSONValue` had already been deleted; the three remaining names (`JSONObject`, `JSONArray`, pydantic's `JsonValue`) do not collide even case-insensitively, no post-generation casing patch exists, and generation is byte-identical across consecutive runs. Investigating it did surface a live break, recorded in [decisions/one-way-to-generate-types.md](decisions/one-way-to-generate-types.md).

* Done and removed: **step creation takes spec objects**. `create_step` and `create_transform_step` already took `NewStepSpec`; only `create_combined_step` was the outlier, which is why it carried a `PLR0913` noqa. It now takes `CombinedStepSpec` and the noqa is gone. Added [decisions/boolean-operator-is-a-type.md](decisions/boolean-operator-is-a-type.md).

- Bundle created. Seeded from the R1-R6 graph rewrite session: the backlog that survived it, and the five decisions taken during it that are not recoverable from the code.

* **The DeRisi empty-branch item was retired by measurement rather than by a fix.**
  Its three candidate causes were tested live on plasmodb.org against
  `GenesByMicroarraypfal3D7_..._Percentile`, holding everything else constant:
  `any_or_all=any` at the top 10 percent over the fourteen trophozoite hours
  returns **871**, `all` returns **233**, and the looser top-20-percent forms
  return 1741 and 486. None is zero, so neither the any/all binding, nor the
  percentile tightening, nor the sample count empties the branch. The two ways
  to bind it wrongly both fail **loudly**: a sample set read under one
  profileset and sent under another is a 422 naming the terms that do not exist
  there (`23 Hour`, `29 Hour` are 3D7-only), and a branch term instead of leaves
  is the `countOnlyLeaves` 422. The step in the strategy that prompted the item
  reads **942**, not 0. The zero in that conversation was the phyletic-profile
  step, which is WDK-SITE-002 (`veupathdb-py: docs/knowledge/wdk/rules/site-model-params.md`) and understood.
  What survives is smaller and already filed elsewhere: that step bound
  `profileset_generic` to WDK's default `DeRisi HB3 Smoothed` rather than the
  3D7 set the request named.

* **Seven backlog items closed in one pass, and three of them by measurement
  rather than by code.** The orphan-delete ordering, the lossy search-config
  write, the verb-blind POST retry, the one-sided range, the two analysis-status
  defects and the logout credential were fixed with tests. The DeRisi empty
  branch, the doomed auth refresh and half of the FRAME budget item turned out
  not to be defects: the first does not reproduce (871 genes live), the second
  was already fixed and tested, and the third's "partial progress is discarded"
  half was already handled - only its report said otherwise.

  The three heuristics tried against the parameter-resolution benchmark were all
  refuted by it, which is the benchmark doing its job: holding a numeric default
  back whenever the request mentions a number costs 14 correct answers to save
  2, and grouping the ends of a range costs 7 to save none. What shipped is the
  one form that scored at parity on exact and one better on wrong.

  `SILENT` is at zero unenforced again, 30 of 31, having been reopened by the
  five site-model rules the phyletic research added.

* **The wire protocol got a consumer, and the consumer got a suite that fails
  when the page changes.** `@pathfinder/assistant-client` is built from
  `PROTOCOL.md` and not from the app it replaces: a dependency-free core that
  reads the frames section 3 defines, refuses the shapes it does not, resumes on
  the cursor rule of section 4 and reduces a turn by the rules of section 9;
  one module that subclasses the AI SDK's transport, because `useChat` takes a
  class; and one named `legacy`, because the durable-task endpoint frames a
  third shape the protocol tells a client to reject. The app deleted five
  modules and imports them instead, so there is one reduction and one framer in
  the repository rather than two.

  The gate is a generator and a comparison, and it was measured rather than
  asserted: adding one row to the document's chunk table failed the sync test
  with `+ "checkpoint"`, and regenerating the capture then failed the reducer
  test with the same word. A protocol change now has two ways to be caught and
  no way to be silent.

  Three things the port found, all of them in code that was passing its own
  tests. A chunk kind the SDK's schema did not know killed the whole turn,
  which is exactly what section 10's additive rule exists to prevent - the
  client now drops what its protocol version does not define and hands the rest
  on. The snapshot reader knew one of the three log envelopes, so a
  `system-message` or `assistant-message` row would have reached a reducer that
  had no place for it. And the cursor advanced only at turn boundaries for a
  reason that lived in a comment; it is now a function with a name and a test
  that says a mid-turn cursor names a chunk whose `start` the client would not
  have.

* **The streaming status line now measures its own silence, and a hung
  request fails instead of waiting forever.** A shared one-second clock
  (`statusClock.ts`) drives the thinking placeholder: after ten silent
  seconds the label reads "Planning, 2m 40s" and counts up, so a slow model
  is distinguishable from a dead pipeline without reading the event table.
  Server side, every LLM path (Lead, sub-agents, compactor, title
  generator) carries a 900-second request timeout through
  `build_model_settings`.

* **The Progress rail no longer covers the thread, the consult card is
  usable by keyboard, and a double-click on Send no longer cancels the turn
  it started.** The rail's overlay mode is deleted - the panel is always
  in-flow and the chat column shrinks; consult option buttons carry
  `aria-label`/`aria-pressed` and the note field a real name; the composer
  ignores a Stop click within 500ms of the Send that started the turn. The
  writes observed after a user stop (title, turn-stopped, finish, done,
  epilogue) were investigated and are the protocol's turn closers, by
  design - no change.

* **The usage surfaces say their scopes.** Trace chip = this turn, composer
  footer = this conversation (visible "Conversation ·" prefix, focusable
  tooltip), QuotaPill = the account month (scope line in its tooltip). The
  remaining cross-surface e2e reconciliation stays on the backlog.

* **A long dispatch now compacts its own in-run history instead of dying on
  the token ceiling.** `compact_exhausted_history` is a third
  `ProcessHistory` processor in `PHASE_HISTORY_PROCESSORS`, so it runs on the
  Lead and on FRAME, BUILD and VERIFY. Past an estimated 100k tokens it keeps
  the head request and the last eight response/request pairs, and collapses
  everything between them into one digest appended to the head request as an
  extra `UserPromptPart` - one line per tool exchange, capped at 4000
  characters, tail-biased. Only complete pairs are dropped, so no orphan tool
  call reaches a provider, and the result still ends with a `ModelRequest`.
  The digest holds no clock reading, which makes the processor a pure
  function of its input and its output a fixpoint; a history of any other
  shape is returned untouched. Proven by
  `tests/unit/ai/agents/test_compact_history.py`: a 50-exchange history at
  125k estimated tokens compacts to 21k, the eight newest pairs survive
  verbatim, call ids and return ids stay equal, and the compacted list round
  trips through `ModelMessagesTypeAdapter`.

* **The three usage surfaces are proven to reconcile, at three levels.** A
  vitest gate imports the real `turnUsageOf` and `aggregateSessionUsage` and
  asserts one message's parts read to the same tokens and cost on the turn
  chip and the conversation footer, that two turns sum into the footer, and
  that a budget-stopped dispatch's tokens contribute to both (the
  wipe-regression pin). A Playwright spec on the mock stack proved the live
  wiring: after one scripted turn the chip's formatted totals equal the
  footer's, and the quota endpoint's token count grew (mock cost is zero by
  design, so the account assertion is token growth). The budget-stop shape
  itself is produced and pinned by the backend unit suite; the mock stack
  cannot cheaply hit a ceiling, so the e2e run uses a plain build turn and
  the stopped-dispatch arithmetic is carried by the vitest gate.

* **A change to how the steps combine is now an in-place edit.**
  `operations_for` plans the shape the edited spec states: when the resolved
  root is not the strategy's own root, or when the structure moves a transform
  onto another input, the pass re-plans from the live graph as one
  `ReplaceSubtreeOp` at the root, over a tree that reuses the step id of every
  leaf and of every combine whose ordered input pair the new shape leaves
  alone. The push planner diffs trees rather than reading operations, so the
  unchanged leaves are skipped and only the combines are recreated - the
  request that used to answer "requires replacing the current strategy" now
  rewires it and keeps every leaf's WDK id. Four shapes are still refused and
  the refusal names which: a criterion the spec keeps left out of the tree, a
  step the strategy does not hold, a step adopted from outside the strategy
  under edit, a step left disconnected. The edit work order prints the shape
  the strategy has now as an indented tree, and tells FRAME that a request
  about how the steps COMBINE is a `set_structure` call over the same criterion
  ids. `SpecDiff.touched_count` counts a rewire as one touch and `render` names
  it, so a rewire beside a criterion change no longer suppresses enrichment and
  no reply can report a rewire as "nothing changed". Proven by
  `tests/unit/domain/strategy/test_spec_to_operations_rearrange.py` (the
  rearrangement plans as one replacement, every leaf id survives, the combine
  whose inputs do not move keeps its own, a moved transform is rewired, and
  three of the refusals) and `tests/unit/ai/lead/test_edit_work_order.py`.

* **Stated combination logic is now typed, gated and verified; a combine
  rewire is an in-place edit.** A user's "A OR B" lands as a
  ConstraintKind.COMBINATION requirement (from the intent gate and from
  consult answers), FRAME's set_structure refuses a tree whose matched
  criteria meet at the wrong operator, and a success verdict over a
  violating structure is corrected to STRUCTURE_VIOLATION - three layers,
  one pure checker (domain/strategy/combination_check.py). The edit path
  plans a re-nest as one ReplaceSubtreeOp over the live leaves (ids and
  values kept, push planner skips unchanged leaves), the edit work order
  prints the current shape, and "cannot re-nest" is no longer claimed.
  Adversarial verification then hardened both: the meeting-node walk counts
  distinct criteria so a duplicated leaf cannot spoof the gate, a new
  combination over the same criteria supersedes the old one so a changed
  mind cannot brick set_structure, and the turn briefing grounds
  combinations against the built tree via spec_from_ast. Known limit: three
  or more terms are checked at the meeting node only (see the backlog).
