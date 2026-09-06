---
type: Proposal
title: How EDA fits PathFinder's architecture
description: Where every EDA concern lands in the layer model, how an EDA compute maps onto the durable-tool machinery piece by piece, how EDA capabilities reach the MCP/SDK program as an admitted tool source, and the single Pydantic model set that keeps the analysis spec from being written three times.
tags: [eda, pathfinder, architecture, layering, durable-tools, mcp, sdk, proposal, ssot]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: accepted
---

# How EDA fits PathFinder's architecture

Status: built. It deepens
[pathfinder-integration-concept.md](pathfinder-integration-concept.md), which
states the two seams; this document states where each piece of code goes, which
existing mechanism it reuses, and what it must not duplicate.

Every PathFinder claim below cites a file read in this repository on
2026-08-27. Every EDA claim cites `veupathdb-py: docs/knowledge/eda/what-eda-is.md`,
`veupathdb-py: docs/knowledge/eda/eda-wdk-bridge.md`, `veupathdb-py: docs/knowledge/eda/rest-surface.md` or
`veupathdb-py: docs/knowledge/eda/genomics-and-wdk-relations.md`, each of which
names its upstream.

## The position in one paragraph

EDA needs no new architectural concept in PathFinder. It needs one integration
client, one service package, thin tool wrappers, one durable job, and one
namespace in the stream-part registry. The reason is that EDA's two hard parts
are already solved here for WDK: a typed client over a foreign REST surface
whose schema we do not own, and a long asynchronous job that must survive a
closed tab. The genuinely new work is authoring the analysis document, and its
architectural weight is a single Pydantic model set with two serialization
boundaries.

## 1. Layering

PathFinder's layer rule is `transport -> services -> domain + integrations ->
persistence`, enforced by the import-linter contracts in
`apps/api/pyproject.toml:257-324`. EDA lands as follows.

### 1.1 `integrations/eda/` - the typed client

Owns every HTTP call to `https://{site}/eda` and every model of its wire
shapes. Bound by the contract "Integrations never import services, transport,
or AI" (`apps/api/pyproject.toml:303-313`).

The precedent to copy exactly is `integrations/veupathdb/wdk_models.py`, whose
base is

```python
class WDKModel(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, extra="ignore", frozen=True)
```

and which carries roughly forty hand-written subclasses of it. An `EdaModel`
base with the same three settings is the right shape for the same three
reasons: `extra="ignore"` survives an upstream field addition, `frozen=True`
makes a fetched study tree safe to share across a turn, and the camel alias
generator matches EDA's wire casing as it matches WDK's.

Modules, and the endpoints each covers (see
`veupathdb-py: docs/knowledge/eda/rest-surface.md`):

| Module | Owns |
|---|---|
| `models.py` | `EdaModel` base; the study / entity / variable / collection tree; the 7-member filter union under `Discriminator("type")`; `Analysis` and `NewAnalysis` with their `descriptor`; `Computation`; `AppInfo`; the permissions map |
| `client.py` | `/studies`, `/studies/{id}`, `/studies/{s}/entities/{e}`, `/permissions`, `/count`, `/tabular`, `/distribution`, `/root-vocab`, `/apps`, `/computes/{name}`, `/apps/{app}/visualizations/{viz}`, `/jobs/{id}` |
| `analyses.py` | `/users/{uid}/analyses/{project}` CRUD, `/public/analyses`, `/import-analysis` |

No new credential path. The EDA service accepts the same registered WDK token
PathFinder already holds: `integrations/veupathdb/auth_login.py:60`
`password_login` returns it, `platform/context.py:6`
`veupathdb_auth_token_ctx` carries it per request,
`platform/security.py:75` sets it, and the worker re-installs it with
`jobs/auth_context.py::attach_wdk_auth`. Guest calls to `/eda` are 401
(measured, `veupathdb-py: docs/knowledge/eda/rest-surface.md`), so
[the registered-login rule](../decisions/wdk-requires-registered-login.md)
covers EDA unchanged.

### 1.2 `domain/eda.py` - the pure part, and it is small

`domain/` is pure by contract (`apps/api/pyproject.toml:257-271` forbids
`httpx`, `sqlalchemy`, `fastapi` and every other layer). Its current contents
are `parameters/`, `research/`, `scratchpad/`, `strategy/`, `search.py`,
`wdk_values.py`.

**The analysis-spec model belongs in `integrations/eda/`, not in `domain/`.**
The argument, and it is a real fork:

*The case for `domain/`.* The analysis document is the central concept of the
whole integration, it has a closed algebra (filters compose by AND across an
array), and PathFinder authors it rather than merely reading it. All three are
true.

*Why it loses anyway.* Three reasons, in order of weight.

1. **Its correctness criterion is a live wire sample, not a rule we can state.**
   The document is valid exactly when the EDA user service stores it and
   `AbstractEdaGenesPlugin` parses it. A pure layer cannot falsify that, so a
   model there would be a shape nothing in the pure layer can test.
2. **It carries an upstream misnomer that must survive verbatim.** The spec's
   `studyId` field holds a DATASET id, and the plugin says so in its own
   comment (`AbstractEdaGenesPlugin.java:199`: "misnamed; still need to look up
   study ID"), as does its mismatch error ("Note both values should be dataset
   IDs, not study IDs (old API)"). A domain type would invite a truthful
   rename, and then two boundaries would need a mapping that exists only to
   undo the rename. Wire misnomers belong at the wire.
3. **The existing precedent is unambiguous.** WDK's own most conceptual
   shapes - `WDKStepTree`, `WDKSearchConfig`, `WDKStep` - live in
   `integrations/veupathdb/wdk_models.py`, while `domain/parameters/specs.py`
   and `domain/parameters/values.py` hold PathFinder's own pure parameter
   model. The split is not "important goes in domain"; it is "ours goes in
   domain, theirs goes at the boundary".

*What is genuinely domain work.* One thing: the pure predicates over a fetched
study tree. Given an entity tree and a filter array, decide whether every
filter names an entity and a variable that exist, whether a `stringSet` value
is in that variable's vocabulary, whether a `numberRange` is inside the
variable's range, and whether the tree contains exactly one
`VEUPATHDB_GENE_ID` variable (the bridge's hard requirement,
`veupathdb-py: docs/knowledge/eda/eda-wdk-bridge.md`). Those are functions of two values with
no I/O, they are the checks that decide whether a step is worth creating, and
they need unit tests without a network. `domain/eda.py` holds them; it takes the
integration models as arguments and imports nothing.

That inversion has a precedent too: `domain/parameters/canonicalize.py` and
`vocab_utils.py` are pure functions over parameter shapes the integrations
layer fetched.

### 1.3 `services/eda/` - the business logic

Bound by "Services never import transport or AI"
(`apps/api/pyproject.toml:293-302`). Three concerns, three modules:

- **`catalog.py` - the study catalog.** Resolve dataset to study through
  `/permissions`, never by deriving it: measured live, `STUDY_<suffix>` equals
  `DS_<suffix>` for only 684 of 747 curated studies, and a shipped search
  (`GenesByRNASeqpfal3D7_Lee_Gambian_ebi_rnaSeq_RSRCWGCNAModules`, dataset
  `DS_eeca6a5476`, study `STUDY_fd06cb37d3`) is a counterexample
  (`veupathdb-py: docs/knowledge/eda/genomics-and-wdk-relations.md`). Owns study
  search and the entity/variable browse an agent needs at run time.
- **`authoring.py` - analysis authoring.** Builds a `NewAnalysis` from live
  study metadata, runs the `domain/eda.py` predicates, then verifies with
  `POST /count` before anything is created. This is the same trust posture as
  parameter validation: one proposer, one validator
  ([the decision](../decisions/one-proposer-one-validator.md)).
- **`compute.py` - compute orchestration.** Submits and polls
  `/computes/{name}?autostart=true`, reads
  `/apps/{app}/visualizations/{viz}`. Called from the worker impl, not from a
  tool. Section 2.

Also in services: the search-catalog side must learn that a search is
EDA-backed. **The detection rule is parameter presence, never the name.**
Measured live on plasmodb.org, 68 of 359 `transcript` searches declare
`eda_analysis_spec` and only 13 have `Eda` in the name; a name filter finds 13
of 68. The catalog already holds every search's parameter list
(`integrations/veupathdb/wdk_models.py::WDKSearch`), so this is a predicate over
data it has, added in `services/catalog/`.

### 1.4 `ai/tools/` - thin wrappers only

The contract "AI tools never import integrations or persistence directly"
(`apps/api/pyproject.toml:283-292`) means an EDA tool cannot call the client,
not even for a one-line `/count`. Every tool goes through `services/eda/`.

Four tools carry the whole authoring loop, and they map onto patterns that
already exist:

| Tool | Shape it copies |
|---|---|
| `search_eda_studies` | `ai/tools/standalone/catalog.py:41` `search_for_searches` - retrieval plus a discovery-gate write |
| `browse_eda_variables` | `ai/tools/standalone/catalog_discovery.py:83` `get_parameter_options` - a vocabulary read with a per-turn dedup ledger |
| `set_eda_filters` | `ai/tools/standalone/frame_spec.py:476` `set_criterion` - the validator raises `ModelRetry` against a sheet the model read earlier in the same turn |
| `run_eda_compute` | `@durable_tool`, section 2 |

### 1.5 `persistence/` - references only

PathFinder stores a reference to the upstream artifact and nothing else. The
EDA user service is the SSOT for an analysis, exactly as WDK is for a strategy;
the precedent is
[a conversation is a thread, its strategy is an attachment](../decisions/conversation-thread-and-strategy-split.md),
where `conversation_strategies` holds the attachment and WDK holds the
strategy. An `analysisId` from `/users/{uid}/analyses/{project}` plus the
`studyId` (that is, the dataset id) is the whole row. Storing the descriptor
would create a second copy that drifts the moment the researcher edits the
analysis on the VEuPathDB site.

### 1.6 What must not go in `assistant-core`

The boundary is an installation fact, not a convention:
`assistant-platform/packages/assistant-core/pyproject.toml` names no `pathfinder` dependency, and
`assistant-platform/packages/assistant-core/tests/unit/test_package_boundary.py` pins the import
surface ([the runtime is a package](../decisions/the-runtime-is-a-package.md)).
CLAUDE.md states the placement rule directly: "anything that names a gene, a
strategy, a WDK search or a phase role goes in `ai/`".

So **no module in `assistant_core/` may name a study, an entity, a variable, a
filter type, a compute or `VEUPATHDB_GENE_ID`.** Nothing about EDA needs to.
The two runtime seams EDA uses are already generic:

- **The stream-part registry.** `assistant_core/conversation/stream_parts/registry.py`
  is an open registry whose `_schema_name` maps `data-<ns>.<name>` to an
  identifier by replacing `.` and `-` (design doc
  `docs/design/2026-08-23-mcp-and-sdk-program.md` section 1.2). PathFinder
  registers `data-eda.*` kinds from the product side; the runtime learns a
  string, not a concept.
- **The tool-source declaration.** `assistant_core/mcp/declaration.py`
  `ToolSourceDeclaration` carries `name`, `source_id`, `tools`, `required`,
  `always_approve` and nothing domain-shaped. Section 3.

## 2. An EDA compute is a durable tool, piece by piece

`veupathdb-py: docs/knowledge/eda/what-eda-is.md` records the job lifecycle:
`POST /computes/{name}?autostart=true` returns a status in
`queued | in-progress | complete | failed | expired | no-such-job`, and the job
is keyed by a hash of its inputs so identical requests share a cached result.
`veupathdb-py: docs/knowledge/eda/eda-wdk-bridge.md` records what happens if a step is
created too early: `GeneEdaVizWithComputePlugin` throws WDK's
`DelayedResultException` on `queued` or `in-progress`.

That is why the compute is driven before the step exists, and PathFinder
already owns the machinery. The mapping, naming the real mechanisms:

| Step | Mechanism, with its file |
|---|---|
| 1. The agent calls `run_eda_compute` | `@durable_tool(tool_name="run_eda_compute", estimated_duration_seconds=...)`, `ai/tools/durable.py:40` |
| 2. A task row is created | `create_background_task(...)` -> `background_tasks`, `services/tasks/background.py:40`, called at `ai/tools/durable.py:65` |
| 3. A job is deferred | `procrastinate_app.configure_task(name=f"durable:{tool_name}", queue="verification", lock=str(conversation_id))`, `ai/tools/durable.py:74-78`. The lock is the conversation, so the resume takes the same lock a chat turn takes |
| 4. The run defers | the decorator records a `DurableDeferral` on the agent's deps and raises `CallDeferred` (`ai/tools/durable.py`); the run ends with `DeferredToolRequests`, the node parks a `PendingDurableCall` (every durable call of the step, per CLAUDE.md's Durable Background Tasks), and `AsyncPostgresSaver` checkpoints the thread. No `interrupt()`, no node replay |
| 5. The turn ends cleanly | `data-background-task-started` inside the turn, `finishReason: "other"` (CLAUDE.md, Durable Background Tasks) |
| 6. The worker runs the real body | `jobs/impls/eda_compute_impl.py`, registered by `register_tool("run_eda_compute", ...)` in `jobs/impls/__init__.py::register_all_tools:24-34`; dispatched by `TOOL_REGISTRY.get(tool_name)` in `jobs/runner.py::_run_durable_task_inner` |
| 7. The impl holds the user's credential | `attach_wdk_auth(veupathdb_auth_token)` in `jobs/runner.py::_run_durable_task_inner`. The token rides in the job payload because the procrastinate hop drops `ContextVar` state (`jobs/runner.py::run_durable_task`). EDA takes the same token, so this needs no change |
| 8. The impl polls and reports | it calls `services/eda/compute.py` and emits `await progress.update(percent=..., message=..., data=...)`, the shape `jobs/impls/control_tests_impl.py:47-86` uses. `TaskProgressEmitter` writes `task_progress` rows and fires `pg_notify("task_progress:<conversation_id>", ...)` |
| 9. The result lands | `_to_dict(payload)` then `repo.mark_result_ready(...)` on the `background_tasks` row (`jobs/runner.py::_run_durable_task_inner`); `repo.mark_resuming(...)` follows once the completion turn opens (`jobs/completion_turn.py::_run_completion_turn`) |
| 10. The thread records the outcome | `_announce_completion` appends `task_completed_event(...)` to `conversation_events` before the completion turn opens (`jobs/runner.py::_announce_completion`) |
| 11. The turn continues | `jobs/completion_turn.py::_run_completion_turn` opens a NEW turn carrying every parked task's `DurableTaskResult`; its chunks are written by `ChatEventWriter` under the parked turn's message id, into the same `conversation_events` rows the dispatcher replays |

**Where the step gets created, and why not in the impl.** The impl returns the
compute's identity and its statistics summary; it creates no step. Two reasons,
both structural rather than stylistic. First, a `jobs/impls/` module has a
worker-side `Context` and no `StrategySession`, so it cannot mutate the turn's
strategy graph - `run_control_tests_on_step_impl` is the model here, taking a
`wdk_step_id` and returning a result dict
(`jobs/impls/control_tests_impl.py:25-87`). Second, the resume exists precisely
so the suspended tool call returns a value the model acts on: after step 11 the
agent is running again, with the compute's result in hand, and it then calls the
ordinary non-durable step-creation tool. Because the EDA job is keyed by its
input hash, that later `POST /computes` inside
`GeneEdaVizWithComputePlugin` hits `complete` immediately, and WDK's
`DelayedResultException` is never reached. **The cache is what makes the
two-phase shape correct rather than merely convenient.**

Two notes on the open edges:

- `queue="verification"` is what the existing durable pair uses. An EDA compute
  is a different workload; whether it wants its own queue is a capacity
  question no measurement here answers. `UNVERIFIED:` the right queue.
- The delayed state the two-phase shape avoids is now measured
  (`veupathdb-py: docs/knowledge/eda/notebook-presets.md`): the answer API returns
  HTTP 202 `{"message":"WDK-DELAYED-RESULT","status":"accepted"}` while the
  compute runs, and the WDK request itself auto-starts the job. The two-phase
  shape stands, now on evidence rather than caution.

## 3. EDA in the MCP/SDK program

The program is `docs/design/2026-08-23-mcp-and-sdk-program.md` (design, paper
only, with an executed-in-repo addendum at section 8) and
`docs/design/2026-08-24-mcp-sdk-execution-plan.md` (batches A through G, run
2026-08-24/25). EDA is placed in their terms.

### 3.1 EDA is a second admitted source, and it is theirs to write

The program's one-page decision (section 0) is: "A VEuPathDB team writes an MCP
server in Java, Kotlin or R, deploys it their own way, and an assistant on the
runtime declares that it wants that server's tools." The assessment's layer
model names EDA explicitly in L3: "MCP servers owned by science teams, any
language: Java/Kotlin on `lib-jaxrs-container-core` (EDA, WDK records, VDI,
...)" (`docs/assessment/2026-08-17-veupathdb-assistant-platform-assessment.md`
section 3.1). `service-eda` is exactly such a service.

So a `veupathdb-eda-mcp` source is the design doc's **P5, "the second server"**
(section 8.2), whose exit criterion is "a second team ships a server without a
PathFinder engineer in the loop". PathFinder's half is an admission record and
a declaration, both of which already have their shapes:

```python
AdmissionRecord(
    source_id="veupathdb-eda-mcp",
    endpoint=...,
    credential_mode="veupathdb_user",
    part_namespace="eda",
    max_call_seconds=60,
)
```

against `assistant_core/mcp/admission.py:12-23`, installed by the host through
`install_admitted_sources(...)` (`admission.py:66`) exactly as
`pathfinder/platform/tool_sources.py::admitted_tool_sources` installs the WDK
record today. The decision
[the admitted tool sources are installed by the host](../decisions/admitted-tool-sources-are-installed-by-the-host.md)
fixes that seam: the set is a value, installed once at process start, with no
argument a request could travel through. The related decision
[PathFinder admits veupathdb-wdk-mcp from two settings, and only with both](../decisions/pathfinder-admits-its-own-mcp-server-from-two-settings.md)
fixes the shape of the configuration: an endpoint and its credential, both
required, so half a configuration admits nothing. An EDA source follows both
without amendment.

### 3.2 The credential mode has only one answer

`credential_mode` must be `veupathdb_user`, the design doc's named deviation
(section 2.4), and the reason is measurable rather than a preference.

`GET /eda/permissions` returns a **per-user** map: `perDataset` is documented as
omitted entirely when the caller is neither a provider nor an end user of any
dataset (`service-eda` `schema/library.raml`,
`PermissionsGetResponse`). `AbstractEdaGenesPlugin.findStudyId` resolves a
dataset id to a study id out of that map and nothing else
(`AbstractEdaGenesPlugin.java:403-410`). A `service` credential would therefore
resolve a **different** `perDataset` set than the user's, so the same analysis
spec would resolve to a different study, or to nothing, depending on which
identity asked. That is not a permissions nicety; it is the resolver.

The design doc's own justification transfers unchanged: the receiving server is
operated by VEuPathDB, validates the token against the same JWKS it came from,
and needs that exact credential because the upstream service will accept no
other identity. Ask 3 of section 7 is the same ask for EDA: until
`auth.veupathdb.org` can mint audience-bound tokens per resource (RFC 8707) or
support token exchange (RFC 8693), `veupathdb_user` on an operator allowlist is
the only mode that works.

### 3.3 Approval, and where the compute goes

The predicate is design doc section 2.2, implemented as
`assistant_core/mcp/approval.py::build_approval_predicate`, reading
`ToolAnnotationsView`. Applying its four rules to EDA:

| EDA tool shape | `readOnlyHint` | `destructiveHint` | Approval |
|---|---|---|---|
| study / entity / variable / vocabulary reads, `/count`, `/distribution` | true | absent | none (rule 3) |
| `POST /computes/{name}?autostart=true` | false | false | asks (rule 4) |
| analysis CRUD under `/users/{uid}/analyses/{project}` | false | true on `DELETE` | asks |

A compute submission writes into a shared job cache and spends server compute;
it is additive rather than destructive, which under the predicate still means
it asks. That is the same answer the program already gave
`run_control_tests_on_search` (design doc section 3.1: "additive, it creates and
does not remove ... which under the Section 2.2 predicate means it asks for
approval on every call").

**MCP and durable tools compose; they do not compete.** Design doc section 2.6
rules that "an MCP task is the server's business; durability is ours", and that
"a tool whose realistic duration exceeds the turn budget is an admission
failure: the server must either return quickly with a handle the model can poll
through a second tool, or the binding must be a durable wrapper on our side."
EDA's compute API is already the first of those two shapes - `autostart=true`
returns a status, not a result - so an `eda-mcp` submit tool fits the 60-second
default budget, and the polling is a `@durable_tool` on our side, as in section
2. The one endpoint that may not fit a call budget is `/tabular` over a large
study; that is an admission-record question
(`max_call_seconds`), measured per deployment.

### 3.4 What belongs in the headless SDK: nothing EDA-specific

`assistant-platform/packages/assistant-client-ts` has three rings and the core ring has no runtime
dependencies
([the client package has three rings](../decisions/the-client-is-a-package-with-three-rings.md)).
The core ring is the whole of `PROTOCOL.md` and nothing else. EDA adds no frame,
no cursor rule and no reduction rule, so it adds nothing to any ring.

What it adds instead is `data-eda.*` part kinds in an **open** union. The
assessment specifies that union as
`KnownDataPartKind | (string & {})` with a renderer map merged from an injected
map and `UnknownDataPartError` as the fallback (assessment section 3.2, row
"Data parts"), and the design doc confirms the backend registry accepts the
dotted form (section 1.2). So a host that wants to render an EDA variable
summary registers one renderer; a host that does not, degrades to the unknown
part. **That is the DRY payoff of the program: an EDA capability ships without
a client release.**

The design doc's own example of a namespaced kind is, verbatim,
`"kind": "data-eda.variable-summary"` (section 2.3).

### 3.5 Multi-assistant reuse: a ClinEpiDB assistant is the proof

`ToolSourceDeclaration` is per-assistant with its own tool allowlist. `site_help`
shows the pattern at `apps/api/src/pathfinder/assistants/site_help/spec.py:34-40`:
it declares one source and names three of the sixteen tools that source serves.
A ClinEpiDB assistant declares the same `veupathdb-eda-mcp` source with a
different allowlist, and inherits the credential, the approval predicate, the
untrusted-output wrapper and the per-turn session with no code in common with
PathFinder.

Zero genomics coupling, structurally, because the genomics-specific half is not
in the source. The bridge is: `VEUPATHDB_GENE_ID`, the dataset-to-presenter
mapping, `eda_analysis_spec` as a WDK parameter, and step creation. All four are
PathFinder's own in-process tools over `services/eda/` plus
`services/strategies/`, not tools on the EDA source. ClinEpiDB has no gene
column and no strategy, and it needs none of them.

The runtime plumbing for a one-agent assistant is already decided:
[a declared tool source reaches a one-agent assistant through its deps](../decisions/a-declared-source-reaches-a-one-agent-assistant-through-its-deps.md),
and [a tool source's session belongs to the turn](../decisions/a-tool-source-session-belongs-to-the-turn.md)
(`ResolvedToolSources` at `assistant_core/mcp/resolution.py:64` opens and closes
every declared source around the whole drive).

### 3.6 What PathFinder should not export

`veupathdb-wdk-mcp` exists as a product module,
`apps/api/src/pathfinder/mcp/`, serving sixteen tools
([the wdk-mcp server is a product module of the api](../decisions/the-wdk-mcp-server-is-a-product-module.md)).
It is tempting to add EDA tools to it. **Do not.** The execution plan's
placement rule is that `pathfinder/mcp/` calls `pathfinder.services.*`
(execution plan section 1.2), so an EDA tool there would make PathFinder a
proxy in front of a Java service that should publish its own MCP endpoint, and
the program's whole argument - "the science stays with its owners" - would be
inverted for the one domain that is most obviously theirs. The exception, if any
is needed as a bridge before P5 lands, is a **bridge tool** rather than an EDA
tool: something like `create_eda_backed_step`, which is genuinely PathFinder's
because it needs WDK step creation. Even that is an in-process tool first; it
becomes an MCP tool only if a second consumer asks.

## 4. Separation of concerns and DRY

### 4.1 The analysis spec appears three times; one model set is the SSOT

The same JSON document is: (a) the body stored by the EDA user service under
`/users/{uid}/analyses/{project}`, (b) the string value of the WDK
`eda_analysis_spec` parameter, (c) the thing PathFinder authors. **One Pydantic
model set in `integrations/eda/models.py` is the SSOT, and there are exactly two
serialization boundaries.**

- **To EDA**, as a request body: `model_dump(by_alias=True, mode="json")`.
- **To WDK**, as a parameter value: the document must arrive as a JSON
  *string* inside a `dict[str, str]`. `WDKSearchConfig.parameters` is typed
  `dict[str, str]` with `coerce_numbers_to_str=True`
  (`integrations/veupathdb/wdk_models.py:51-68`), and a coercion of a nested
  model to a string is not something Pydantic should be asked to invent. So
  `services/eda/authoring.py` calls
  `model_dump_json(by_alias=True, exclude_none=True)` once and hands the
  service layer a string. **The tool never serializes.** One call site, so
  there is one answer to "what exactly went into the parameter".

Three fields carry traps that the model must encode rather than smooth over:

- `studyId` holds a dataset id (`DS_*` or `EDAUD_*`). Keep the name; state it in
  the field docstring. Renaming it to `dataset_id` would need a mapping at both
  boundaries whose only purpose is to undo the rename.
- The plugin requires `spec.studyId == eda_dataset_id` when both are present
  (`AbstractEdaGenesPlugin.java:203-207`), so a `@model_validator(mode="after")`
  on the step-request model is the right place for that check, not a call-site
  `if`.
- An empty `eda_analysis_spec` is legal and means "no filters": the plugin
  synthesizes a full empty descriptor
  (`AbstractEdaGenesPlugin.java:157-183`). So the authoring path must be able
  to emit the empty string, and must not emit `"{}"`.

### 4.2 The catalog embedding pattern, reused for studies

`integrations/embeddings/semantic_index.py` already holds the whole shape:
`SearchIndexEntry` with its enriched text, and `SemanticSearchIndex.query`
ranking against it. As of [embeddings are an API call and a Postgres record
manager](../decisions/embeddings-are-an-api-and-a-record-manager.md) the vectors
live in the shared record manager under `catalog:{site_id}`, not in a per-site
`.npz` file, and there are no query and document prefixes. The consumer is
`services/catalog/semantic_matching.py::apply_semantic_bonus:41`, which reads
the index off the site catalog via `catalog.get_semantic_index()`
(`services/catalog/discovery.py:264`).

A study index is the same object over different text:
`displayName + shortDisplayName + description` per study. Two things must
change, and both are measured facts rather than guesses:

- **The invalidation key is the study `sha1hash`, except when it is empty.**
  Live, all 12 `user_submitted` studies on plasmodb.org carry
  `"sha1hash": ""`. A user study must key on `lastModified` instead. This
  corrects [pathfinder-integration-concept.md](pathfinder-integration-concept.md),
  which says "Any cached copy needs the study `sha1hash` as its invalidation
  key" without the exception.
- **The candidate set is not `/studies`.** Live, `/permissions` carried 880
  dataset entries against 759 studies; 121 datasets had a `studyId` with no
  `/studies` row, and 0 studies were missing from `/permissions`. `/studies` is
  the browsable catalog and the right thing to index; `/permissions` is the
  resolver and the access gate. Two calls, two purposes, and the index must not
  be used to resolve.

### 4.3 The `params_template` pattern, reused for compute configs

`ai/tools/standalone/frame_spec.py:129` declares
`params_template: dict[str, None]`, and the instruction that goes with it is
"The result's `params_template` is the exact `params` object to send back"
(pinned by
`tests/unit/ai/agents/test_frame.py`). The decision behind it
is [one proposer, one validator](../decisions/one-proposer-one-validator.md):
the model reads the whole sheet and answers every slot once, and the per-slot
resolvers that read English were deleted.

A compute configuration is the same problem with different content. A
`differentialexpression` compute needs a `collectionVariable`
(`{entityId, collectionId}`), two comparator groups, and thresholds. The
template's keys must come from the app's declared configuration - `GET /apps`
returns every app with its visualizations - and never from model memory. The
upstream notebook presets are the reference for which slots a family actually
needs:
`web-monorepo/packages/libs/eda/src/lib/notebook/notebooks/` holds
`differentialExpression.tsx`, `wgcnaCorrelation.tsx`, `antibodyArray.tsx`,
`boxplot.tsx` and `differentialAnalysisReview.tsx`, and the `edaNotebookType`
question property is what selects one (three values live:
`differentialExpressionNotebook` on 53 searches, `antibodyArrayNotebook` on 5,
`wgcnaCorrelationNotebook` on 1).

### 4.4 What not to duplicate from upstream, and the drift mitigation

The io-ts definitions in
`web-monorepo/packages/libs/eda/src/lib/core/types/{analysis,filter}.ts` and the
RAML in `service-eda` `schema/library.raml` are upstream truth. PathFinder's
Pydantic models are a mirror, and a mirror drifts.

**The drift risk is not hypothetical, and it is already measured in two places.**

1. `GET /eda/permissions` and `GET /eda/studies` disagree on the casing of the
   same field: `sha1Hash` in the first, `sha1hash` in the second.
2. The RAML declares `DatasetPermissionEntry` with `shortDisplayName` and
   `description` required and `additionalProperties: false`. Live, 24 of 880
   entries omit one or both. **The RAML is a document, not a validator for the
   wire.**

**The mitigation is the shape `assistant-platform/packages/assistant-client-ts` already uses
against `PROTOCOL.md`.** That package vendors a capture of the document,
regenerates it with `yarn sync:protocol`, and a suite test regenerates and
compares, so a document change fails the gate rather than passing silently
([the client package has three rings](../decisions/the-client-is-a-package-with-three-rings.md),
"What was rejected", last-but-one entry). For EDA the artifact to pin is not a
document but a **live wire sample**: a recorded response per endpoint, checked
into the test tree, with a hermetic lane that validates the models against the
fixtures and a live lane that re-fetches and fails on an unmodelled required
field. That is the two-lane shape the science layer already runs
(`docs/knowledge/conventions/verification-gates.md`, and design doc section 4.2
for the same split applied to conformance).

## 5. Type generation: hand-write the mirrors

The question is whether `integrations/eda/models.py` is hand-written or
generated from `service-eda`'s RAML. **Hand-write it**, consistently with how
PathFinder already mirrors WDK. Five reasons, the first two decisive:

1. **A generator would produce a model that rejects real responses.** RAML says
   `additionalProperties: false` and marks fields required; PathFinder needs
   `extra="ignore"` and tolerant optionality, because 24 of 880 live permission
   entries omit a declared-required field. Generating and then patching the
   output is the "one way to generate types" failure this repository already
   ruled against
   ([the decision](../decisions/one-way-to-generate-types.md)).
2. **The existing pattern is hand-written and load-bearing.**
   `integrations/veupathdb/wdk_models.py` carries roughly forty `WDKModel`
   subclasses over WDK's REST surface, by hand, on a `CamelModel` base. Two
   mirroring styles in one integrations layer would be a second answer to the
   same question.
3. **We call a small fraction of the surface.** `service-eda`'s `api.raml` is
   about 2,100 lines of resources and `schema/library.raml` about 3,460 lines of
   types; most of it is MicrobiomeDB and MapVEu visualization payloads
   PathFinder will never request. Generating all of it produces dead types that
   still have to be reviewed and still break the build when upstream edits them.
4. **The filter union is better by hand.** Seven members discriminated on
   `type` is exactly what `Discriminator("type")` is for, and a generated
   version of a tagged union tends to arrive as an untagged `Union` that
   Pydantic then has to guess at.
5. **The one place a schema is authoritative is per-tool, and the program
   already handles it.** An `eda-mcp` tool declares an `outputSchema` and
   returns `structuredContent` against it, and the runtime registers that
   schema as the part's payload schema at admission "so the part flows into the
   generated OpenAPI index and the open TypeScript union with no hand-written
   model" (design doc section 2.3). Generated types belong there, where a
   passing conformance report backs them, not over a document nobody validates
   against.

Rejected alternative, named: a drift test that fetches `library.raml` at test
time and asserts our field sets are a subset of it. It couples the suite to the
network and to a document the wire already contradicts. Pinned wire samples
(section 4.4) test the thing that actually breaks.

## 6. What this document changes about the concept doc

[pathfinder-integration-concept.md](pathfinder-integration-concept.md) stands.
Three of its statements get sharper here, and one needs a correction; none is
contradicted.

- **Corrected.** "Any cached copy needs the study `sha1hash` as its
  invalidation key" - true for curated studies, and `sha1hash` is the empty
  string for all 12 `user_submitted` studies live on plasmodb.org. A user study
  keys on `lastModified`.
- **Sharpened.** "the catalog should mark searches carrying `eda_analysis_spec`
  as EDA-backed" - correct, and now quantified: 68 of 359 searches on
  plasmodb.org, of which a name-based filter would find 13.
- **Sharpened.** "`studyId` in the spec must equal `eda_dataset_id`" - correct,
  and both are DATASET ids; the field is misnamed upstream and the plugin says
  so in its own comment.
- **Sharpened.** "the EDA job model maps one-to-one onto `background_tasks`" -
  correct, and section 2 above names each of the eleven mechanisms and states
  why the step is created after the resume rather than inside the impl.
