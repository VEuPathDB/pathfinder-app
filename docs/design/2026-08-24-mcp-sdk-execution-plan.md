# The MCP and SDK program: execution plan (2026-08-24)

> Status: **EXECUTED, batches A through G, closed 2026-08-25.** What each batch
> landed is recorded in `docs/knowledge/log.md`: batch A under 2026-08-24, and
> batches B through G under 2026-08-25. Batches A through F carry an accepted
> `model=fable` review; batch G ran the pilot turn and this reconciliation. The
> plan below is left as written, because it is the document the batches executed
> from; where a batch decided differently, the log entry says so. What did not
> land: section 5's decision points 1, 2, 6 and 7 are the owner's. Point 4 was
> settled on 2026-08-27 by fork (a), an in-process budget:
> `docs/knowledge/decisions/per-site-catalogs-are-evicted-and-the-warm-up-does-not-block-the-bind.md`.
>
> This document turns the design decided in
> `docs/design/2026-08-23-mcp-and-sdk-program.md` into batches an implementation
> agent can execute and a reviewer can verify. It plans code in this repository
> only; the reference Java server (design doc section 5) and everything behind
> the VEuPathDB meeting (section 7) are out of scope here. Every claim about
> current code below was verified against the working tree on 2026-08-24 and is
> cited as `path:line`. Where the design doc and the code disagree, the
> disagreement is named in section 5, never silently overridden.
> Implementation agents are Opus; every batch ends with a `model=fable`
> reviewer rerunning the full ladders (section 3, per batch).

Three corrections to the design doc's ground truth, found while verifying, so
no agent plans from stale facts:

1. **The P1 prerequisite it names is already closed.** The design doc (section
   8.2 and Appendix B4) blocks P1 on "`single_agent_graph` cannot ask for
   approval". That backlog item no longer exists; the runtime now owns the
   deferred-tool cycle in
   `assistant-platform/packages/assistant-core/src/assistant_core/graph/approvals.py:25-76`,
   `single_agent_graph` runs it (`graph/single_agent.py:90-106` builds the
   resume turn, `:220` parks the approval), and PROTOCOL.md 1.2.0 records the
   change (`assistant-platform/PROTOCOL.md:732`). The debt inverted: the
   cycle now exists **twice**, because the Lead still carries its own copy
   (`apps/api/src/pathfinder/ai/graph/_lead_turn.py:82-308`;
   `docs/knowledge/backlog/approval-cycle-is-written-twice.md`). Batch A folds
   it.
2. **PROTOCOL.md is 1.2.2, not 1.0.0/1.1.0** (`PROTOCOL.md:3`). Both gaps the
   design doc's section 6.4 says "are ours to close" are closed: the request
   side is section 12 and the durable-task lifecycle is section 6.1, with the
   per-task channel specified as deprecated legacy in section 13. No batch
   below re-plans them.
3. **The design doc does not commit to "the worker refuses to build semantic
   indexes".** `docs/knowledge/backlog/worker-memory-grows-unbounded-with-sites-touched.md:4`
   attributes that proposal to "the MCP design doc"; the design doc contains no
   such statement (verified by search over the whole document). What it does
   commit to is the split-tool pattern (section 3.1, "Four tools are split, not
   moved"), from which an index-placement decision *follows* but was never
   taken. Section 5 makes it an explicit decision point; batch D lands the
   uncontroversial half (memory ceilings), batch F lands the recommended half
   (eviction) unless the owner overrides.

---

## 1. Target architecture

### 1.1 What exists when the program is done

```
assistant-platform/packages/assistant-core            the runtime (existing, version 0.2.0a1)
  src/assistant_core/mcp/          NEW: declarations, admission, approval
                                   predicate, wrapper stack, per-turn
                                   resolution. Imports pydantic-ai + mcp only.
  PROTOCOL.md 1.3.x                + data-turn-failed (batch F3). Additive.
  (dependency change)              pathfinder-shared dependency REMOVED; the
                                   two runtime stream-part models move in
                                   (batch F1), so the package publishes alone.

assistant-platform/packages/assistant-client-ts       the headless client (existing, 0.1.0-alpha.1)
  dist/ build + publish pipeline   NEW (batch F2). ./legacy ring KEPT (1.4.2).

assistant-platform/packages/mcp-conformance           NEW package: the conformance suite as a
                                   runnable pytest plugin (design doc section
                                   4). Depends on mcp/httpx/pytest only; never
                                   imports pathfinder or assistant_core.

apps/api/src/pathfinder/mcp/       NEW module: veupathdb-wdk-mcp, a FastMCP
                                   streamable-HTTP server over the extracted
                                   service functions. Runs as its own
                                   container on the api image with its own
                                   entrypoint (python -m veupathdb_mcp).

apps/api, apps/web                 existing apps; batch A/B4/C/F3/F4/G changes.
```

### 1.2 Placement rules, and why each artifact lives where it does

- **The MCP consumption path is runtime code**, so it goes in
  `assistant_core/mcp/`. The three reasons are the design doc's own (section
  2.1): the credential is the runtime's, the approval predicate is a
  deployment safety property, and admission is operator configuration. The
  package boundary is already physical: `assistant-platform/packages/assistant-core/pyproject.toml`
  names no pathfinder dependency (`pyproject.toml:6-20`), and
  `tests/unit/test_package_boundary.py` pins its import surface. New code
  there inherits both proofs.
- **The wdk-mcp server is product code**, so it goes in
  `apps/api/src/pathfinder/mcp/`. Its sixteen tools call
  `pathfinder.services.*` (section 1.4); a separate distribution would have to
  depend on the whole app to reach them, which is the packaging lie the
  assessment rejected (assessment section 3, "a Python package would have
  exactly one consumer"). The server is not the runtime and never imports
  `pathfinder.assistants` (import-linter contract 7,
  `apps/api/pyproject.toml:329-340`, gains `veupathdb_mcp` as a source
  module).
- **It runs as its own container, not a route on the api app.** Same image,
  second entrypoint. Isolation of memory (the per-site catalogs and semantic
  indexes it will hold are exactly what OOM-killed the api once,
  `docs/knowledge/backlog/worker-memory-grows-unbounded-with-sites-touched.md`),
  independent restart, and parity with VEuPathDB's one-service-one-container
  idiom (assessment 1.3). Decision point 3 records the alternative.
- **The conformance suite is its own package** because its consumer is a
  foreign team running it against a Java server on their CI (design doc 4.2).
  A suite that imports pathfinder cannot be handed over. Its dependency rule
  is enforced the same way assistant-core's is: a boundary test walks its
  modules and asserts no `pathfinder` and no `assistant_core` import.
- **The server-side FastMCP dependency already exists**: `fastmcp-slim` 3.3.1
  in the api venv ships the full server
  (`apps/api/.venv/.../fastmcp/server/server.py:287` defines `class FastMCP`),
  and `mcp` 1.27.0 pins protocol revision 2025-11-25 (design doc Appendix A).
  assistant-core's tests need the same for the in-process server; batch B1
  adds the explicit dependency after verifying which extra provides
  `pydantic_ai.mcp` (do not guess; read the installed dist-info).

### 1.3 Packaging and versioning: the second-consumer story

The program's point is a consumer outside this repo. Today neither package can
be handed over:

- `assistant-core` 0.2.0a1 depends on `pathfinder-shared` as an editable path
  (`assistant-platform/packages/assistant-core/pyproject.toml:19,22-23`). The dependency carries
  exactly two modules - `shared_py.stream_parts.background_task` and
  `shared_py.stream_parts.turn_usage` - pinned by
  `tests/unit/test_package_boundary.py:24-25` and imported only from
  `graph/stream_events.py:11` and `conversation/stream_parts/core_parts.py:3-8`.
  Those models (`TaskProgress`, `TaskCompleted`, `TurnUsage`) are the payloads
  of the runtime-owned parts `data-task-progress`, `data-task-completed`,
  `data-turn-usage` (`PROTOCOL.md:154-164`), so they belong in the runtime.
  **Batch F1 moves them into `assistant_core` and deletes the dependency**, at
  which point the package builds and publishes alone (hatchling build already
  configured, `pyproject.toml:25-30`).
- `@pathfinder/assistant-client` 0.1.0-alpha.1 exports raw TypeScript sources
  (`assistant-platform/packages/assistant-client-ts/package.json`, `"exports"` mapping to
  `./src/*.ts`) and has no build step. **Batch F2 adds a `dist/` emit and
  points `exports` at it**, keeping the three-ring shape recorded in
  `docs/knowledge/decisions/the-client-is-a-package-with-three-rings.md`.
- Versioning follows the protocol: PROTOCOL.md is additive within a minor
  (`PROTOCOL.md:486-496`); each package minor-bumps with a protocol minor.
  Publish target (PyPI vs GitHub Packages vs git tag) is decision point 2; the
  batches produce publish-ready artifacts and a `--dry-run` proof either way,
  so no batch blocks on the choice.

### 1.4 The sixteen tools, verified against the tree

Every design-doc inventory row was re-verified. MCP name maps to the source
symbol; two rows are renames the brief must carry explicitly, one is new code.

| MCP tool | Source symbol (verified) | Notes |
|---|---|---|
| `list_record_types` | `ai/tools/standalone/catalog.py:26` `get_record_types` | rename |
| `search_for_searches` | `catalog.py:41` | split: retrieval half only; gate at `catalog.py:83-101` stays |
| `browse_search_categories` | `catalog.py:106` | registered in NO toolset today; batch A1 decides build-or-drop first |
| `list_searches` | `catalog.py:126` | split: gate at `catalog.py:139-143` stays |
| `list_transforms` | `catalog.py:147` | registered in NO toolset today; batch A1 |
| `lookup_phyletic_codes` | `catalog.py:163` | |
| `search_example_plans` | `catalog.py:184` | |
| `get_search_overview` | `catalog_discovery.py:92` | split: `AlreadyReadNotice` dedup `:109-117`, `register_search` `:141`, goal read `:138` stay |
| `get_parameter_options` | `catalog_discovery.py:164` | split: read-dedup ledger `:206-218` stays |
| `lookup_gene_records` | `gene.py:16` | |
| `resolve_gene_ids_to_records` | `gene.py:45` | in NO toolset today (only named by VERIFY's prose, `ai/agents/verification.py:67`); batch A1 registers it before it may ship |
| `get_step_estimated_size` | `ai/tools/standalone/execution.py:16` `get_estimated_size` | rename |
| `get_step_sample_records` | `results.py:69` `get_sample_records` | rename; `record_type` becomes an argument (today read off `strategy_session`, `results.py:86-88`) |
| `get_step_download_url` | `results.py:26` `get_download_url` | rename |
| `run_control_tests_on_search` | `experiment.py:96` | the only writer; asks approval under the predicate |
| `enrich_gene_ids` | NEW (batch C3) | `run_gene_set_enrichment` (`workbench.py:149`) keys on PathFinder's store and is durable; not exportable as-is |

What stays internal is the design doc's section 3.2 list, re-confirmed at the
seams it cites (`frame_spec.py` binding tools; strategy mutation in
`toolsets/execution.py:103-130`; the durable pair `experiment.py:63`,
`optimization.py`; memory tools; the Lead's own tools,
`ai/lead/lead_agent.py:254-269`).

### 1.5 Dependency and verification surface per artifact

| Artifact | May import | Must never import | Own gate |
|---|---|---|---|
| `assistant_core/mcp/` | assistant_core, pydantic-ai, mcp, fastmcp (tests only) | pathfinder, shared_py (after F1) | package ladder (section 3, ladder R) + boundary test |
| `pathfinder/mcp/` | pathfinder.services, pathfinder.platform, fastmcp, mcp | pathfinder.assistants, pathfinder.transport, pathfinder.ai | api ladder (ladder P) + contract 7 extended + its own integration lane |
| `assistant-platform/packages/mcp-conformance` | mcp, httpx, pytest, pydantic | pathfinder, assistant_core | own pyproject ladder (ladder C, defined in E1) + boundary test |
| `assistant-client-ts` | none at runtime (core ring) | react, app code | yarn test / typecheck / lint (ladder T) |

---

## 2. Separation ledger

Every conversation-vs-science-vs-logic boundary this program touches. "Proof"
is the artifact that fails when the separation breaks.

| # | Boundary | Separated today (proof) | This program | Stays coupled on purpose |
|---|---|---|---|---|
| 1 | Runtime vs science | Package boundary: `assistant-core` pyproject names no pathfinder; `tests/unit/test_package_boundary.py`; contract 7 (`apps/api/pyproject.toml:329-340`) | MCP resolution, admission, approval predicate and credential attach all land runtime-side (`assistant_core/mcp/`), so an assistant declares and never holds | The wdk-mcp server itself is science and imports services freely; it is a product artifact, not a runtime one |
| 2 | Wire protocol vs both UIs | `PROTOCOL.md` 1.2.2 pinned by `tests/integration/conversation/test_protocol_document.py`; consumer side pinned by `assistant-platform/packages/assistant-client-ts/tests/conformance/` (11 suites) | One additive part (`data-turn-failed`, F3); packages become installable outside the repo (F1, F2) | The AI SDK chunk vocabulary itself; changing it is a protocol major and out of scope |
| 3 | Approval cycle: runtime vs Lead | HALF-separated - the defect this program cannot ship over. Runtime copy: `assistant_core/graph/approvals.py:25-76`, run by `single_agent.py:90-106,220`. Lead's second copy: `_lead_turn.py:82-149` (`pending_approval`, `resume_message_history`, `resume_deferred_hint` duplicate the runtime's three) | Batch A2 folds the duplicated halves onto the runtime functions. An external consumer cannot trust a predicate the flagship bypasses | The four Lead-only behaviours stay in `ai/`: sub-agent re-entry (`resolve_pending_approval`, `_lead_turn.py:255-308`; decided in `docs/knowledge/decisions/sub-agent-approvals-re-enter-the-sub-agent.md`), dispatch-answer fan-out, `typed_reply` + `is_pure_approval` (`_lead_turn.py:180-191`), sibling answers (`:206-227`). They are product approval *semantics*, not the cycle |
| 4 | Tool retrieval vs discovery gate | NOT separated: four tools do a WDK read then write `agent_state` (section 1.4 rows) | Batch C1 extracts pure service halves (site + args -> result); the in-process wrappers keep the gate; the MCP server calls the same service functions | The gate itself (`record_catalog_searches`, `register_search`, read-dedup): it is the turn |
| 5 | Credential vs assistant code | Runtime/worker hold the WDK token (`jobs/payloads.py` carries it; `attach_wdk_auth` context); assistants never read it | MCP credential attaches at `MCPToolset` construction inside the runtime resolver (B3); `credential_mode` is admission config; the deny-list of things a server must never receive (design doc 2.4) becomes a test | `veupathdb_user` passthrough remains a named spec deviation until VEuPathDB answers Ask 3; implemented but refused unless an admission record explicitly names it |
| 6 | Sub-agents vs the turn | NOT separated: `frame_agent`/`execution_agent`/`verification_agent` are module singletons with toolsets baked at import (`ai/agents/frame.py:131`, `execution.py:179`, `verification.py:147`; consumed via `SUB_AGENT_BY_ROLE`, `ai/lead/sub_agent_tools.py:55-59`) while the Lead is per-turn (`lead_agent.py:243`) | Batch B4 makes all three per-turn factories, the precondition for any per-user toolset reaching them (design doc 2.1) and parity with `docs/knowledge/decisions/the-agent-belongs-to-the-turn.md` | |
| 7 | Durable-task channel | Thread log carries the whole lifecycle (PROTOCOL 6.1); the per-task SSE dialect is specified-deprecated (section 13) but the web app still opens it (`apps/web/src/features/conversation/content/parts/useTaskEventStream.ts` via `lib/sse/typedEventStream.ts:7`, the only importer of the client's `./legacy` ring) | Batch F4 moves the task card onto message parts and deletes the app's per-task subscription | The `./legacy` ring and `typedEventStream.ts` stay: `features/workbench/api/streaming.ts` reads experiment/sweep streams that are not thread events. The per-task HTTP route stays byte-for-byte (`docs/knowledge/decisions/durable-task-progress-belongs-in-the-thread-log.md`) |
| 8 | Checkpoint state vs reader | HALF-separated: the allowlist exists (`assistant_core/conversation/serde.py:34-56`) but `graph.aget_state` reads decode outside it, and `CombineOp`/`PhaseDisposition` are on no list (`docs/knowledge/backlog/aget-state-bypasses-the-checkpoint-allowlist.md`) | Batch A3 fixes the read path and completes `PATHFINDER_CHECKPOINT_TYPES` (`apps/api/src/pathfinder/assistants/pathfinder_spec.py:51-65`) | |
| 9 | Tool surface vs instructions/extractors | NOT separated: VERIFY's instructions name three tools its toolset lacks (`ai/agents/verification.py:64-68` vs `ai/tools/toolsets/verification.py:91-122`); `browse_search_categories`/`list_transforms` are named by `ai/context/extractors.py` (`_SEARCH_DISCOVERY_TOOLS`, around `:194-200`) but registered nowhere; `update_search_decision` (`catalog_selection.py:44`) is referenced only by `devtools/diagnosis.py:164` | Batch A1: one decision per tool plus an agreement test, because the MCP inventory ships two of these orphans and an inventory built on unregistered tools is untested surface | |

**Backlog items this program does NOT absorb, and why.** Everything in the "UI
run investigations", "Agents" (except A1's item), "WDK integration",
"Verification gates" and "Chat" sections of `docs/knowledge/backlog/index.md`
other than the six named above: they are product-behaviour and harness debt
with no bearing on whether a second consumer can trust the runtime or the tool
boundary. Named explicitly so scope cannot creep: `frame-budget-does-not-scale`,
`eval-scoring-is-exact-match-only`, `hidden-required-default-chooses-the-science`,
`chat-turn-hangs-for-half-an-hour`, `e2e-suite-residual-failures`,
`worker-heartbeat-starves-during-turn`, the web/api lint-job items, and all
seventeen UI-run items. They stay ranked where they are.

---

## 3. Batch decomposition

Seven batches, A through G. Rules applied: every batch's ladder is green on its
own; destructive flips are atomic inside one batch (A1's deletion, B4's
singleton flip, F1's model move, F4's file deletions); no batch strands debt a
later batch is needed to remove - where a later batch finishes a story, the
earlier batch is complete and correct without it (D2 ships ceilings that stand
alone; F-eviction extends, not repairs).

**The gate ladders, named once** (from
`docs/knowledge/conventions/verification-gates.md`, restated so a blank-slate
agent needs no other file):

- **Ladder R (runtime package)**, from `assistant-platform/packages/assistant-core/`:
  `uv run ruff check src tests` ; `uv run ruff format --check src tests` ;
  `uv run mypy --strict src` ; `uv run pytest` (starts a
  `pgvector/pgvector:pg16` testcontainer unless `DATABASE_URL` is set).
- **Ladder P (api)**, from `apps/api/`: `uv run ruff check src/` ;
  `uv run ruff format --check src/` ; `uv run mypy --strict src/pathfinder/` ;
  `uv run pyright src/pathfinder/` ; `uv run lint-imports` ;
  `uv run pytest src/pathfinder/tests/ -q`.
- **Ladder W (web)**, from `apps/web/`: `npx tsc --noEmit` ;
  `npx eslint src/` ; `node scripts/check-boundaries.mjs` ; `npx vitest run`.
- **Ladder T (client package)**, from `assistant-platform/packages/assistant-client-ts/`:
  `yarn test` ; `yarn typecheck` ; `yarn lint`.
- **Ladder C (conformance package)**, from `assistant-platform/packages/mcp-conformance/`
  (created in E1): `uv run ruff check src tests` ; `uv run mypy --strict src` ;
  `uv run pytest`.
- **Ladder K (knowledge)**, from repo root: `node scripts/check-knowledge.mjs`.
- **Docker verification**, when a container behaviour changed:
  `docker compose --env-file .env.dev up -d --build --force-recreate api worker`
  then grep for a new symbol INSIDE the container before trusting any manual
  test (`verification-gates.md:117-123`).

Baselines: before its first change, every task records the current pass count
of each ladder it will run (`uv run pytest ... -q | tail -1` etc.). Acceptance
is: same-or-higher pass count, zero failures, zero new skips. Do not hardcode
counts from this document; the tree moves.

| Batch | Goal (one sentence) | Tasks | Ladders | Needs docker? |
|---|---|---|---|---|
| A | The trust base: the approval cycle exists once, the checkpoint read path honours the allowlist, and every named tool is callable | A1, A2, A3 | P, R, K | no |
| B | The tool protocol lives in the runtime: declared sources resolve into credentialed, approval-wrapped, per-turn toolsets, proven against an in-process server | B1, B2, B3, B4 | R, P, K | no |
| C | The sixteen tools' service seam: pure retrieval halves, MCP auth, and the new enrichment-by-value service | C1, C2, C3 | P, K | no |
| D | veupathdb-wdk-mcp is served: sixteen tools over streamable HTTP in its own container, with memory ceilings landed | D1, D2, D3 | P, K, docker | D2, D3 yes |
| E | The conformance suite is a package a foreign team can run, and it is green against our server | E1, E2, E3 | C, K (+docker in E3) | E3 yes |
| F | The packages publish alone and the protocol debt is paid: shared-py cut, client built, failed turns visible, one channel per thread | F1, F2, F3, F4 | R, P, T, W, K | F3 partially |
| G | Second-consumer proof: an assistant that is not PathFinder answers with a tool served over MCP, approval included, end to end | G1, G2 | P, W, K, docker | yes |

Ordering and concurrency: **A first** (it touches the same seams B modifies).
**B and C run concurrently** (different packages/layers). **D after B+C.**
**E1/E2 concurrently with D** (the suite is written against an in-process
reference server; E3 needs D). **F concurrently with D/E** except F3's e2e
half. **G last.** Critical path: A2 -> B1..B3 -> D1 -> D3 -> G1.

**Fable review, every batch.** The reviewer gets the batch's task briefs and
this checklist, and must be able to run it with no other context:

1. Rerun every ladder the batch names, from the stated directories. Compare
   with the baselines recorded in the batch report. A count that went down, a
   new skip, or a flaky rerun is a rejection.
2. Read every file the briefs name as created/modified. Check the CLAUDE.md
   absolute rules mechanically: no `# type: ignore`/`as any`/eslint-disable,
   no `import X as Y` (except third-party name conflicts), no backwards-compat
   aliases or re-exports, comments 1-3 lines ASCII with no incident narration,
   no TODOs added, no debug instrumentation left.
3. Adversarial checks per batch (listed with each batch below).
4. Grep for stranded debt: every symbol the batch made unreachable is deleted
   in the same batch; `grep -rn` each deleted symbol's name to prove zero
   references remain.
5. Knowledge bundle: the batch's backlog items are DELETED (file + index line)
   in the same change that closes them; decisions with a real alternative are
   recorded under `docs/knowledge/decisions/`; ladder K green.
6. Verify no `.env*` file was read or printed anywhere in the batch's logs.

**Rollback story, every batch.** The user owns git; agents never run git
commands. Rejection therefore means: the reviewer names the defects, the batch
stays open, and the implementing agent fixes in place until the checklist
passes - a batch is never "accepted with notes". Because each batch is
independently green and batches touch disjoint seams by construction, a
rejected batch never blocks a concurrent one except along the stated critical
path. If a batch must be abandoned wholesale, the user reverts it as one unit;
briefs keep each batch's edits confined to the files they name so that revert
is clean.

---

## 4. Per-task agent briefs

### 4.0 Standing rules restated for every brief (agents are blank slates)

These restate the repository rules a brief's agent must obey; each brief below
adds only its specifics. An agent executes from its brief plus this section.

- **TDD, no exceptions**: write the named failing test first, watch it fail,
  then implement. Unit tests for pure logic AND integration tests where I/O is
  touched. Mock only the LLM (`PATHFINDER_CHAT_PROVIDER=mock`); WDK and
  Postgres are real in integration lanes. The api unit tier blocks sockets
  (`verification-gates.md:26-30`); tests needing a DB go under
  `tests/integration/`.
- **Python 3.14**: `except ValueError, TypeError:` without parens is VALID
  (PEP 758). Do not flag, do not "fix".
- **Comment rules**: 1-3 lines, simple present tense, ASCII only, no
  incident/history narration, no restating signatures. Near-zero new comments;
  delete narration after each edit.
- **No type suppressions, no `import as`** (except genuine third-party name
  conflicts), **no backwards-compat aliases**, no `isinstance`/`getattr`/
  `dict.get` chains where a Pydantic model does the work
  (`model_validate`, `extra="ignore"`, validators, discriminators).
- **Library surfaces are read, not guessed**: before calling any pydantic-ai,
  fastmcp or mcp API, open the installed source under
  `apps/api/.venv/lib/python3.14/site-packages/` (or the package's own venv)
  and cite the line in the task report. The design doc's Appendix A line
  references are a map, not a substitute for reading.
- **Machine traps**: chat turns run in the WORKER, not the api - after any
  change to agent/tool/mock code, rebuild AND force-recreate both
  (`docker compose --env-file .env.dev up -d --build --force-recreate api worker`),
  then grep the new symbol inside the container; `up -d --build` alone can
  leave the old container running. Docker builds on this machine can fail on
  the credential helper - if `docker build` errors on credentials, bypass with
  a clean `DOCKER_CONFIG` (an empty config dir) for the build. The first chat
  POST of a fresh process pays the PIGuard ONNX load and can exceed enqueue
  timing assumptions (`docs/knowledge/backlog/first-chat-post-of-a-fresh-process-pays-the-piguard-load.md`);
  never assert timing on the first POST. The IDE's pyright may flag
  `assistant_core` imports that the CLI run accepts; the gate is the CLI run
  from `apps/api/`, never the IDE surface. One 11.42 GiB Docker VM: do not run
  the e2e stack and heavy builds simultaneously; api warm is ~5-6 GiB and the
  worker grows with sites touched.
- **Never read or print `.env*` contents.** Reference `$VAR` names only.
- **Docs in the same change**: a task that closes a backlog item deletes the
  item file and its `backlog/index.md` line in the same change; a choice with
  a real alternative gets a `docs/knowledge/decisions/` entry; ladder K after.
- **Report format**: recap leads with remaining debt (or the words "zero
  debt"), then evidence: commands run, tail of output, baselines vs after.

---

### Batch A - the trust base

Adversarial review focus for the batch: run one real approval arc through the
devtools debugger (`pathfinder.devtools.chat`, mock provider, in the api
container) for BOTH assistants - PathFinder's `consult_user`/`clear_strategy`
path and site_help's runtime path - and diff the chunk logs against PROTOCOL
section 6.2. Then grep `_lead_turn.py` for any function whose body duplicates
an `assistant_core.graph.approvals` function.

#### A1. Tool-surface reconciliation (closes `verify-instructions-name-tools-it-cannot-call.md`)

**Why (2 sentences).** VERIFY's instructions chain three tools its toolset
cannot call, so every controls-needing verification wastes a model turn; and
the MCP inventory (section 1.4) ships `resolve_gene_ids_to_records`,
`browse_search_categories` and `list_transforms`, which today are registered
in no toolset - an inventory of unregistered tools is surface nobody has ever
run. This task makes every named tool callable or deletes the name, then pins
the agreement so the three lists cannot drift again.

**Decisions to implement (build-or-drop, per tool).**
- `resolve_gene_ids_to_records` (`ai/tools/standalone/gene.py:45`): REGISTER
  into the verification toolset (`ai/tools/toolsets/verification.py:91-122`),
  together with `lookup_gene_records` (`gene.py:16`) and `literature_search`
  (`research.py`), exactly the chain `ai/agents/verification.py:64-68`
  instructs. It ships over MCP; it must be a tool real turns exercise.
- `browse_search_categories` (`catalog.py:106`) and `list_transforms`
  (`catalog.py:147`): REGISTER into the FRAME toolset
  (`ai/tools/toolsets/frame.py:57-78`); the context extractor already expects
  their observations (`ai/context/extractors.py`, `_SEARCH_DISCOVERY_TOOLS`)
  and both ship over MCP.
- `update_search_decision` (`catalog_selection.py:44`): DELETE the tool and its
  module if nothing else remains there, and update its only reference
  (`devtools/diagnosis.py:164`) to stop looking for it. It is registered
  nowhere and superseded by the `set_criterion` flow.

**Files.** `ai/tools/toolsets/verification.py`, `ai/tools/toolsets/frame.py`,
`ai/agents/verification.py` (instructions stay, now true),
`ai/tools/standalone/catalog_selection.py`, `devtools/diagnosis.py`,
`ai/context/extractors.py` (only if a name changes), new test file
`tests/unit/ai/test_tool_surface_agreement.py`, backlog file + index line
deleted.

**Tests first.**
- `test_verify_toolset_contains_instructed_gene_chain` - builds the
  verification toolset, collects tool names via the toolset's own listing
  (read `FunctionToolset` in the venv for the accessor; do not guess), asserts
  the three names present. RED today.
- `test_every_instructed_tool_is_callable_by_its_agent` - for each of frame /
  execution / verification / lead: extract backtick-quoted `tool_name(` and
  `` `tool` `` mentions from the agent's instruction constants, intersect with
  a curated allowlist of real tool-name tokens, assert each is in that agent's
  toolset (or Lead tool list, `lead_agent.py:254-269`). Keep the extraction
  dumb and the token list explicit in the test; the point is drift detection,
  not NLP.
- `test_extractor_registry_names_only_registered_tools` - every key of
  `_EXTRACTOR_REGISTRY` and member of `_SEARCH_DISCOVERY_TOOLS` in
  `ai/context/extractors.py` is registered in at least one toolset or on the
  Lead. RED today for the two orphans.
- `test_update_search_decision_absent` - grep-level assertion via import
  failure: the symbol no longer exists.

**Verify.** Ladder P; ladder K. Baseline first (record counts). Run one mock
turn through `pathfinder.devtools.chat run ... --mock` in the api container
afterwards and confirm no tool-not-found retry appears in the run artifacts.

**Traps.** The verification toolset wraps in `DynamicEnumToolset`
(`toolsets/verification.py:123-126`) - new tools must not accidentally gain
enum overrides; `_verification_enum_overrides` (`:46-70`) keys on exact tool
names, leave it alone. `sequential=True` is load-bearing on the durable tools
(`:97-103` and the docstring `:79-86`); do not touch those registrations.
Instructions are prompt text: adding three tools to the toolset changes token
cost, not behaviour contracts - do not rewrite the prose beyond what the
change makes false.

#### A2. Fold the Lead's approval cycle onto the runtime (closes `approval-cycle-is-written-twice.md`)

**Why.** The deferred-tool cycle exists once in the runtime
(`assistant_core/graph/approvals.py:25-76`) and once in the Lead
(`_lead_turn.py:82-149` plus resolution `:255-308`); a fix to one leaves the
other wrong, and an external consumer cannot trust a runtime predicate the
flagship assistant bypasses. After this task the shared four exist once, in
the package, and the Lead keeps only its product semantics.

**The split, decided.** Runtime-owned (target state): building a
`PendingApproval` from a `DeferredToolRequests` (+ history), rebuilding
`DeferredToolResults` from answers, replaying resume history, and the
`DeferredToolHint`. Product-owned, stays in `ai/`: sub-agent selection and
re-entry (`_lead_turn.py:100-118`, `resolve_pending_approval`), the
dispatch-answer fan-out and `typed_reply`/`is_pure_approval` reading
(`:180-191`, `:230-252` - `is_pure_approval` is a PathFinder security
capability), sibling answers (`:206-227`). Rationale: the first four are
protocol mechanics PROTOCOL 6.2 specifies; the rest is Lead orchestration the
protocol does not know.

**Files.** `assistant-platform/packages/assistant-core/src/assistant_core/graph/approvals.py`
(extend: `pending_approval` gains optional `sub_agent` and `user_message_id`
pass-throughs OR - preferred - the Lead constructs `PendingApproval` via the
runtime function and `model_copy(update=...)`s its product fields; pick
whichever leaves ONE construction of the shared fields, and record the choice),
`apps/api/src/pathfinder/ai/graph/_lead_turn.py` (delete
`pending_approval`'s duplicated body, `resume_message_history`,
`resume_deferred_hint`; import the runtime functions), the Lead node that
calls them (follow the imports; `ai/graph/lead_node.py`), plus
`assistant-platform/packages/assistant-core/tests/unit/graph/` for the extended shapes. Backlog
file + index line deleted.

**Types.** `PendingApproval` lives in `assistant_core/graph/turn_state.py` and
is checkpointed (`serde.py:34-42`); fields may be ADDED with defaults, never
removed or retyped - existing checkpoints must keep decoding
(`serde.py:1-11` states why). If a field must move, stop and report instead.

**Tests first.**
- Package side: extend the approvals unit suite - a `DeferredToolRequests`
  with both `calls` and `approvals` produces the same `PendingApproval` the
  Lead's old code produced (port the Lead's existing test cases for
  `pending_approval` into the package as the red tests).
- App side: the Lead's existing approval tests pass UNCHANGED (that is the
  batch's definition of done, from the backlog item: "the Lead's approval
  tests still pass unchanged, and the sub-agent approval arc still resumes").
  Find them with `grep -rn "resolve_pending_approval\|pending_approval" apps/api/src/pathfinder/tests`.
- One new integration test: a sub-agent approval arc driven through the
  builder graph with the mock model, asserting the re-entry still works
  (reuse the existing arc test if one exists; extend it to assert the shared
  functions are the runtime's by identity, e.g. the app module no longer
  defines them).

**Verify.** Ladders R and P, baselines first; ladder K. Then the batch-level
devtools double-arc check (batch header).

**Traps.** `messages` passed to `pending_approval` must be the FULL run
history - the docstring at `approvals.py:31-36` and `_lead_turn.py:95-98`
both state the empty-history resume failure; keep the invariant stated once,
in the package. The checkpoint allowlist (A3) is being modified concurrently
in the same batch: coordinate the `PATHFINDER_CHECKPOINT_TYPES` edit so the
two tasks do not both add types in conflicting hunks - A3 owns that file.

#### A3. The state read honours the checkpoint allowlist (closes `aget-state-bypasses-the-checkpoint-allowlist.md`)

**Why.** `graph.aget_state` decodes checkpoint values outside the msgpack
allowlist `serde.py` exists to enforce, printing eleven deprecation warnings
on types that ARE allowlisted, and `CombineOp`/`PhaseDisposition` are on no
list at all - on the LangGraph release that makes this an error, every thread
inspection (devtools gate detection, eval runner verdict read) breaks while
turns keep working. The runtime is about to be handed to a second consumer;
"state reads work" must be a tested property, not luck.

**Investigation before code (the backlog item's own instruction).** Root cause
is NOT yet established. Read, in the api venv:
`langgraph/checkpoint/postgres/aio.py` (`AsyncPostgresSaver.aget_tuple` - which
serde decodes which columns) and `langgraph/pregel/__init__.py`
(`Pregel.aget_state` - what it materialises that `astream` does not). Only
then choose between: passing the allowlisted serde into the path missing it,
or registering the types where LangGraph actually reads them. Write the
finding into the task report with file:line from the venv.

**Files.** `apps/api/src/pathfinder/assistants/pathfinder_spec.py:51-65`
(`PATHFINDER_CHECKPOINT_TYPES` gains `CombineOp` - import from
`veupathdb.domain.strategy.ops` - and `PhaseDisposition` is already there at
`:53`; verify against the warning list in the backlog item and add exactly
what reaches a checkpoint), whatever the investigation names
(`assistant_core/conversation/checkpointer.py` and/or the devtools/eval read
path), new test
`apps/api/src/pathfinder/tests/integration/ai/test_state_read_allowlist.py`.
Backlog file + index line deleted.

**Tests first.**
- `test_aget_state_read_emits_no_unregistered_type_warning` - drive one mock
  turn on a fresh thread (in-process, integration tier, real Postgres), then
  read the thread through the same path
  `pathfinder.devtools.chat._gate_from_checkpoint` uses, under
  `warnings.catch_warnings()` with the LangGraph deprecation category raised
  to error. RED today with eleven hits (the backlog item's measurement).
- A unit test pinning that `PATHFINDER_CHECKPOINT_TYPES` contains every type
  the domain state can carry into a checkpoint - assert `CombineOp` and
  `PhaseDisposition` membership explicitly.

**Verify.** Ladder P (integration tier included), baselines first; ladder K.

**Traps.** Do not widen the allowlist blindly: a type added here changes what
strict msgpack accepts for EVERY assistant (the union,
`assistant_core/registry.py:76-85`); add only what the warning evidence names.
`TextUIPart` warns despite being in `CORE_CHECKPOINT_TYPES`
(`serde.py:34-42`) - that is the smoking gun that the fix is in the read
path's serde wiring, not the list; if your fix is only list additions, the
red test will still fail and you must keep digging, not skip.

---

### Batch B - the tool protocol in the runtime (design doc P1)

Adversarial review focus: in the package suite, a `destructiveHint: true` tool
and a no-annotations tool BOTH stop at `tool-approval-request` while a
`readOnlyHint: true` tool runs silently; the credential string appears in the
transport construction and in NO deps object, state field, chunk, or log line
(grep the test artifacts for the literal token); after the turn, the toolset's
exit is proven (reference-count or connection assertion, per B3's test); and
`P1`'s exit criteria from the design doc section 8.2 are each named in a test.

#### B1. Declarations and admission (`assistant_core/mcp/`)

**Why.** The assistant declares, the runtime resolves (design doc 2.1): the
declaration is the one field `AssistantSpec` grows, and the admission record
is operator configuration a request can never supply. This task creates both
shapes and the loading path, with no network behaviour yet.

**Files (new).**
`assistant-platform/packages/assistant-core/src/assistant_core/mcp/__init__.py`,
`mcp/declaration.py`, `mcp/admission.py`;
`assistant-platform/packages/assistant-core/src/assistant_core/spec.py` (one field);
`assistant-platform/packages/assistant-core/pyproject.toml` (dependency: whichever extra
provides `pydantic_ai.mcp` - READ
`apps/api/.venv/lib/python3.14/site-packages/pydantic_ai-2.22.0.dist-info/METADATA`
to find it, plus `fastmcp` in the dev group for the in-process test server);
`tests/unit/mcp/test_declaration.py`, `test_admission.py`;
`tests/unit/test_package_boundary.py` (new module's allowed imports).

**Types (copy-paste-ready; adjust only if a gate forces it).**

```python
# assistant_core/mcp/declaration.py
from pydantic import BaseModel, ConfigDict, Field


class ToolSourceDeclaration(BaseModel):
    """One MCP server this assistant asks for. The runtime resolves it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=32)
    source_id: str = Field(min_length=1)
    tools: frozenset[str] | None = None
    required: bool = False
    always_approve: frozenset[str] = frozenset()
```

```python
# assistant_core/mcp/admission.py
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type CredentialMode = Literal["none", "service", "veupathdb_user"]
type ApprovalPolicy = Literal["annotations", "always"]


class AdmissionRecord(BaseModel):
    """One admitted server. Operator configuration, never request data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    credential_mode: CredentialMode = "none"
    part_namespace: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    approval_policy: ApprovalPolicy = "annotations"
    max_call_seconds: int = Field(default=60, ge=1)
    content_trust: Literal["untrusted"] = "untrusted"


class AdmittedSources(BaseModel):
    model_config = ConfigDict(frozen=True)

    records: tuple[AdmissionRecord, ...] = ()

    def resolve(self, source_id: str) -> AdmissionRecord | None: ...
```

`AssistantSpec` grows exactly one declaration
(`spec.py:116-133` today): `tool_sources: tuple[ToolSourceDeclaration, ...] = ()`.
The admitted set reaches the runtime as a host-injected object (the
`use_settings_source` pattern, `assistant_core/platform/config.py:40-63`, is
the precedent: a small `install_admitted_sources(...)` module-level seam, or a
field the host passes where the turn is driven - pick the one that keeps
`AdmittedSources` out of `RuntimeSettings`' env parsing, because an endpoint
list with credentials modes does not belong in flat env vars; record the
choice as a decision entry).

**Tests first.** Duplicate `source_id`s refused; a declaration naming an
unadmitted source resolves to None (policy applied later, in B2's predicate
rule 2); `part_namespace` grammar refusals; `content_trust` literally cannot
be anything else (pydantic proves it); `AssistantSpec` accepts and freezes the
tuple; boundary test still green.

**Verify.** Ladder R, baselines first. Ladder K (decision entry for the
admission-loading seam).

**Traps.** `AssistantSpec` is frozen with `arbitrary_types_allowed`
(`spec.py:119`) - a `frozenset` field on a nested frozen model is fine, but
run mypy strict early; pydantic-settings must NOT pick these up from env
(`RuntimeSettings` has `extra="ignore"`, `config.py:18-23` - do not extend
that class).

#### B2. The approval predicate, the wrapper stack, and the part binding

**Why.** Approval is denied by default and granted only by an admitted
server's `readOnlyHint` (design doc 2.2); results are untrusted content whose
declared payloads become typed parts (2.3, 2.5). This task builds the pure
logic: the predicate, the `UntrustedOutputToolset`, and the fixed wrapping
order, all testable without a network.

**Files (new).** `assistant_core/mcp/approval.py`, `mcp/untrusted.py`,
`mcp/wrapping.py`; `tests/unit/mcp/test_approval_predicate.py`,
`test_untrusted_output.py`, `test_wrapping_order.py`.

**Shapes.**

```python
# assistant_core/mcp/approval.py
from pydantic import BaseModel, ConfigDict


class ToolAnnotationsView(BaseModel):
    """The annotation fields the predicate reads, tolerant of absence."""

    model_config = ConfigDict(extra="ignore")

    readOnlyHint: bool | None = None
    destructiveHint: bool | None = None
    openWorldHint: bool | None = None
    idempotentHint: bool | None = None
```

The predicate is a closure builder
`build_approval_predicate(admitted: AdmissionRecord | None, declaration: ToolSourceDeclaration)`
returning the `(ctx, tool_def, tool_args) -> bool` shape
`ApprovalRequiredToolset` takes (verified:
`pydantic_ai/toolsets/approval_required.py:22-32` per design doc Appendix A -
re-read it in the venv). Rules, in order, from design doc 2.2: (1) name in
`declaration.always_approve` -> True; (2) `admitted is None` or
`admitted.approval_policy == "always"` -> True; (3) annotations parse to
`readOnlyHint is True and destructiveHint is not True` -> False; (4) anything
else -> True. Annotations come from
`tool_def.metadata["annotations"]` (`pydantic_ai/mcp.py:1155-1169`), parsed
with `ToolAnnotationsView.model_validate` - never `dict.get` chains.

`UntrustedOutputToolset` is a `WrapperToolset` subclass (read
`pydantic_ai/toolsets/wrapper.py` first) whose `call_tool`: (a) calls through;
(b) runs an injected scan hook
(`type OutputScan = Callable[[str], Awaitable[ScanVerdict]]`, with a
fence-not-fail default per design doc 2.5 - the hook is a seam; PathFinder
wires PIGuard later, out of this batch's scope); (c) when the tool's
`metadata["meta"]` declares `org.veupathdb.assistant/streamPart`
`{kind, version}`, validates the structured payload against the declared
schema and returns
`ToolReturn(return_value=payload, metadata=[DataChunk(type=kind, data=payload)])`
(mechanism verified: `ToolReturn` from any toolset unwraps,
`pydantic_ai/_tool_execution.py:564-588`; `DataChunk` reaches the wire via
`iter_metadata_chunks`, `pydantic_ai/ui/vercel_ai/_utils.py:171-188`); (d) on
schema-invalid payload: result still returns, NO part, a violation is
recorded through an injected callback. The `kind` must start with
`data-<part_namespace>.` - checked at wrap time, not call time, and the dotted
kind is legal in the registry (`_schema_name`,
`assistant_core/conversation/stream_parts/registry.py:34-40`).

Wrapping order is a function, not a convention:

```python
# assistant_core/mcp/wrapping.py
def wrap_source(toolset, *, admitted, declaration, predicate, scan) -> AbstractToolset[Any]:
    """Approval outside, untrusted-scan inside, filter, prefix, transport."""
```

applying `ApprovalRequiredToolset(UntrustedOutputToolset(FilteredToolset(PrefixedToolset(toolset))))`
per design doc 2.1's fixed order.

**Tests first.** Predicate: a table-driven test over the four rules including
the absent-annotations row and the unadmitted-source row. Untrusted: declared
part validates -> `DataChunk` present; invalid payload -> no chunk, violation
callback fired, result intact; namespace violation refused at wrap time.
Order: build the stack around a stub toolset and assert the outermost type
and nesting by walking `.wrapped`.

**Verify.** Ladder R, baselines first.

**Traps.** `ToolDefinition.metadata` may be None for non-MCP toolsets - the
wrapper stack is only ever applied to MCP sources, but the predicate must not
crash on None metadata (rule 4 catches it). Model the annotations, never
`metadata.get("annotations", {}).get("readOnlyHint")` chains - the
Pydantic-maximalism rule is absolute. Do not import fastmcp in `src/` (it is a
dev/test dependency until B3 proves what the runtime itself needs).

#### B3. Per-turn resolution and lifecycle, proven end to end in the package

**Why.** `MCPToolset` fixes its credential at construction
(`pydantic_ai/mcp.py:848-851`, `:1470-1516`) and is a reference-counted async
context manager (`:1094-1124`), so a per-user credential means a toolset
constructed, entered and closed within one turn (design doc 2.1). This task
threads resolution through the turn seam and proves the whole P1 exit
criterion against an in-process FastMCP server.

**Files.** `assistant_core/mcp/resolution.py` (new):
`ResolvedToolSources` - an async context manager that, given a spec's
declarations, the admitted set, and a credential provider
(`type CredentialProvider = Callable[[AdmissionRecord], str | None]`), builds
the wrapped stack per source and exposes
`by_name: Mapping[str, AbstractToolset[Any]]`; `required=False` sources that
fail to connect resolve to absent, `required=True` raise.
`assistant_core/spec.py`: `TurnContextRequest` (`spec.py:91-101`) gains
`tool_sources: Mapping[str, AbstractToolset[Any]]` defaulting empty, so an
assistant's `build_turn_context` can hand them to its graph.
`apps/api/src/pathfinder/ai/conversation/turn_runner.py`: `run_turn`
(`turn_runner.py:100-135`) enters the resolution around the whole drive (build
before `spec.build_turn_context`, exit after `_drive_graph` returns, in a
`finally`). The package test harness (`tests/synthetic.py` + the drive path
the V2 batch built) gains the same entry so the package proves it without the
app. Tests:
`assistant-platform/packages/assistant-core/tests/integration/mcp/test_in_process_server.py`.

**The in-process server for tests** (fastmcp dev dependency): a `FastMCP` app
with three tools - `read_thing` (`readOnlyHint=True`, an `outputSchema` and a
tool-level `_meta` streamPart declaration, returns `structuredContent`),
`write_thing` (`destructiveHint=True`), `plain_thing` (no annotations).
`MCPToolset` accepts an in-process `FastMCP` server directly
(`pydantic_ai/mcp.py:671-713`) - no network, no docker.

**Tests first (these ARE the design doc P1 exit criteria, named).**
- `test_mcp_tool_appears_in_a_real_turn` - the synthetic assistant declares
  the source; a scripted turn calls `read_thing`; the chunk log carries its
  `tool-input-*`/`tool-output-available` cycle.
- `test_destructive_tool_asks_and_readonly_does_not` - `write_thing` and
  `plain_thing` both park a `PendingApproval` and the wire carries
  `tool-approval-request` (PROTOCOL 6.2); `read_thing` never does.
- `test_declared_payload_becomes_namespaced_part` - the turn's log contains
  `data-<ns>.<name>` with the validated payload.
- `test_result_scanned_before_reentry` - the scan hook sees the output before
  the model does (inject a recording hook).
- `test_toolset_closed_per_turn` - after the turn, the toolset is exited
  (assert via the fastmcp client's state or a counting wrapper; read the
  installed source to pick the observable).
- `test_credential_reaches_transport_only` - the provider returns a sentinel
  token; assert it appears in the constructed transport's headers and in no
  chunk, no state dump, no deps repr.
- App side: one integration test that `run_turn` builds and closes sources for
  a spec that declares none (the zero-source path must cost nothing and
  change no behaviour - regression guard for both existing assistants).

**Verify.** Ladders R and P, baselines first; ladder K (decision entry:
per-turn toolset lifecycle owner is the runner, with the alternative - the
assistant's graph owns entry - named and rejected because a graph that raises
would leak the session).

**Traps.** `iter_sse`/turn framing must not change - the resolution wraps
OUTSIDE the graph drive, and a source failure on a `required=False` source
must not kill the turn (log + absent). Do not let the credential into
`TurnContext` or `AssistantDeps` (`assistant_core/graph/runtime.py:20-55`):
the map handed over contains ready toolsets, never the token. The
`site_help`/`pathfinder` specs declare no sources; their `build_turn_context`
signatures must keep working unmodified (the new request field has a
default).

#### B4. Sub-agents leave their module singletons

**Why.** The three sub-agents are module-level singletons with toolsets baked
at import (`ai/agents/frame.py:131`, `execution.py:179` region,
`verification.py:147-165`), consumed through `SUB_AGENT_BY_ROLE`
(`ai/lead/sub_agent_tools.py:55-59`), while the Lead is built per turn
(`lead_agent.py:243-286`); a per-user, per-turn toolset can never reach a
singleton (design doc 2.1, Appendix B3). This is the named P1 work that makes
PathFinder itself able to consume MCP sources later, and it finishes the
parity the Lead's own decision started
(`docs/knowledge/decisions/the-agent-belongs-to-the-turn.md`).

**Files.** `ai/agents/frame.py`, `ai/agents/execution.py`,
`ai/agents/verification.py`: each module's singleton becomes
`build_frame_agent() -> Agent[...]` (same construction, including the
post-construction `.instructions(...)` registrations at `frame.py:153-159`,
`verification.py:168-176`); `ai/lead/sub_agent_tools.py:55-59`
`SUB_AGENT_BY_ROLE` becomes a factory map
`dict[PhaseRole, Callable[[], Any]]` and its consumers call at dispatch
(`ai/lead/sub_agent_dispatch.py`, follow the imports);
`ai/agents/registry.py:14-25` `phase_defaults` reads baked ids without
constructing live agents where possible (`baked_model_id` currently takes the
agent - constructing one per call in a `phase_defaults()` read is acceptable
if cheap; measure, and if construction is heavy, expose the baked id as a
module constant next to each factory). Every module-level import of the three
singletons is migrated (grep `frame_agent\|execution_agent\|verification_agent`
across `apps/api/src` and tests).

**Tests first.** A unit test per agent: two calls to the factory return
distinct `Agent` objects with equal model ids and tool-name sets (pin the
tool-name set explicitly - this doubles as the tool-surface pin A1 wants);
the existing dispatch tests keep passing; one test that a per-dispatch
`override` on one built agent cannot leak into a second build (the exact
defect the Lead's decision names).

**Verify.** Ladder P, baselines first. Then the docker verification (this
changes worker-executed code): rebuild + force-recreate, grep
`build_frame_agent` inside the worker container, run one mock turn via
devtools.

**Traps.** Agent construction cost: the singletons exist for import-time
cheapness; building three agents per dispatch is fine (the Lead already does
it per turn) but do NOT rebuild inside a retry loop. `defer_model_check=True`
is set on all three (`frame.py:149`, `verification.py:164`) - keep it, or
model resolution starts hitting providers at build time. The mock provider
path resolves the model at dispatch (`sub_agent_tools.py:106-125`) - the
factory change must keep `phase_override_kwargs` semantics identical, or
every e2e mock journey breaks; run one e2e-stack mock journey only if the
unit+devtools evidence is ambiguous (the full suite is out of scope).

---

### Batch C - the service seam for the sixteen tools

Adversarial review focus: for each split tool, diff the in-process tool's
observable behaviour before/after (same WDK fixture in, same payload out,
gate side-effects intact - the fixture lane exists,
`verification-gates.md:36-38`); and confirm the service halves take
`site_id` + arguments only, no `RunContext`, no `agent_state`.

#### C1. Extract the retrieval halves of the four split tools

**Why.** Four tools do a WDK read and then write PathFinder's discovery gate
(design doc 3.1, "split, not moved"; verified at `catalog.py:83-101`,
`:139-143`, `catalog_discovery.py:109-141`, `:199-218`). The MCP server must
serve the read without the gate, and the in-process tools must keep the gate;
one service function under both is the only shape that cannot drift.

**Files.** The retrieval logic largely already lives in
`pathfinder/services/catalog/` (`catalog.search_for_searches` is called at
`catalog.py:73-80`; `read_search_definition` + formatting at
`catalog_discovery.py:118-139`). The task is to ensure a complete, pure
service function exists per exported tool with the exact signature the MCP
server needs (site_id explicit, no deps), moving formatting/validation that
today lives only in the tool body down into `services/catalog/` where
missing. Touch: `services/catalog/searches.py`, `services/catalog/` overview
and parameter modules (follow `read_search_definition` and
`format_search_overview` imports from `catalog_discovery.py`), the four tool
bodies (now thin: call service, then gate). Also expose the goal-independent
overview variant: `format_search_overview` takes the FRAME draft goal at
`catalog_discovery.py:138` - the service half takes `query: str | None`
instead, and the in-process wrapper passes the draft goal.

**Tests first.** Per service function: a hermetic unit test against the pinned
WDK fixture store (`veupathdb.devtools.fixtures` - the recording path,
`verification-gates.md:36-46`; add manifest entries only if an existing
fixture does not cover the read, and record with `yarn wdk:record` which
needs `VEUPATHDB_AUTH_TOKEN` set in the environment, never printed). Per
wrapper: the existing tool tests keep passing, plus one test per gated tool
asserting the gate side-effect still fires (e.g. `record_catalog_searches`
recorded names after `search_for_searches`).

**Verify.** Ladder P, baselines first.

**Traps.** `search_for_searches` appends `_UNIVERSAL_SEARCHES` and hides
decided names (`catalog.py:83-101`) - BOTH are gate-half behaviour; the
service half returns the ranked matches only, and the wrapper composes. Do
not let the service half grow an `agent_state` parameter "for convenience";
the test that it imports nothing from `pathfinder.ai` is part of the task
(assert via import-linter: `pathfinder.services` already may not import
`pathfinder.ai`, `apps/api/pyproject.toml:289-297` - so any accidental
coupling fails ladder P's `lint-imports`).

#### C2. MCP auth: bearer validation and protected-resource metadata

**Why.** The server must refuse a missing/wrong credential as a protocol
error, answer 401 with `WWW-Authenticate` carrying `resource_metadata`, and
publish RFC 9728 protected-resource metadata - which no VEuPathDB service does
today, making this the genuinely new auth work (design doc 4.1 family 2,
5.3). PathFinder already validates the ES512 VEuPathDB bearer for its own API
(`platform/security.py:111-127` `resolve_principal`;
`docs/knowledge/decisions/bearer-identity-and-service-tokens.md`); this task
makes that validation reusable by the MCP server process.

**Files.** `apps/api/src/pathfinder/mcp/auth.py` (new): a dependency that (a)
extracts `Authorization: Bearer`, (b) validates per the same JWKS path the
api uses (reuse the existing verifier - find it from `resolve_principal`'s
imports; do not duplicate the JWKS fetch/cache), (c) maps mode: a VEuPathDB
user token (for `credential_mode: veupathdb_user` tools and the step reads),
or the service-account key for catalog reads (`VEUPATHDB_AUTH_TOKEN`
semantics and its transport guard,
`docs/knowledge/decisions/wdk-requires-registered-login.md` - the guard
refuses `/users/<id>/...` without a request token; the MCP server inherits
it for free by calling the same services). Plus
`pathfinder/mcp/metadata.py`: the RFC 9728 document route
(`/.well-known/oauth-protected-resource`) naming `auth.veupathdb.org`
(configurable), and the 401 challenge builder.

**Tests first.** Unit: header absent -> 401 with `WWW-Authenticate`
containing `resource_metadata=`; expired/garbage token -> same; metadata
document validates against a typed model of RFC 9728's required fields.
Integration (marked, credentialed): a real `WDK_TEST_TOKEN` bearer resolves
to a usable identity. No credential value in any error message or log
(assert on captured logs).

**Verify.** Ladder P, baselines first.

**Traps.** `validateClaims` is empty everywhere in VEuPathDB and PathFinder
does not check `aud` either, for the recorded reason (design doc 2.4 quoting
the decision) - do NOT "fix" audience validation here; it is Ask 3, a
decision point, and unilaterally enforcing `aud` would refuse every real
token. Never log a token; the procrastinate redaction exists for job args
(`jobs/logging_filters.py`) but this is a new surface - write the
no-token-in-logs test first.

#### C3. `enrich_gene_ids`: enrichment by value

**Why.** The exported enrichment tool must take genes by value plus a
background source, because `run_gene_set_enrichment` keys on a PathFinder
store id (`workbench.py:149-174`) no other consumer has; and its result field
names are load-bearing (wrong ones yield an empty column, not an error - rule
WDK-ANS-007, `docs/knowledge/wdk/rules/searches-and-answers.md`). This is new
service code with a conformance case attached.

**Files.** `pathfinder/services/gene_sets/` + the enrichment service (follow
`jobs/impls/geneset_enrichment_impl.py` to the real implementation): add a
service entry point
`enrich_gene_ids(site_id, gene_ids: list[str], background: BackgroundSource, enrichment_types: list[EnrichmentType] | None)`
that reuses the existing ORA machinery without a stored gene set. Typed
result model with the exact wire names: GO `goId`/`goTerm`, Pathway
`pathwayId`/`pathwayName`, Word `word` + `pathwayName` (all under
`resultData`).

**Tests first.** Unit against fixtures for the three field-name families
(these become the conformance case in E2); a bounds test (max gene list
size - mirror `_MAX_GENE_IDS = 200`, `gene.py:13`); integration (marked
live) with a small known set on plasmodb. The June enrichment statistics
fixes are closed (exact hypergeometric, non-finite as None - assessment
status addendum) - the new path must call the SAME stats code, and a test
pins that (no second implementation).

**Verify.** Ladder P, baselines first.

**Traps.** The durable in-process tool (`run_gene_set_enrichment`) stays
untouched - this is an additional service entry, not a refactor of the
worker path. Enrichment durations: the MCP call must fit
`max_call_seconds` - measure on the live test and record the number in the
task report; if a realistic list exceeds the budget, the tool declaration in
D1 must say so (design doc 2.6: a tool that cannot fit the budget is an
admission failure, and the answer is a smaller cap on list size, not a task
bridge).

---

### Batch D - veupathdb-wdk-mcp served

Adversarial review focus: from a scratch client (a 20-line pydantic-ai
script), list tools and diff the full inventory against section 1.4 -
names, annotations, outputSchema presence, `_meta` declarations; call one
tool per credential mode; verify the two-user isolation case yourself with
the two test identities; and `docker stats` before/after ten calls to
confirm the server container, not the api, absorbed the index memory.

#### D1. The FastMCP server module

**Why.** Sixteen tools over streamable HTTP is the deliverable a gene-page
assistant, Claude Code, and the wrangler can call (design doc 3.1); the
server is stateless per call, takes `site_id` explicitly, and declares
annotations honestly because the predicate on the consuming side believes
them only through admission.

**Files (new).** `apps/api/src/pathfinder/mcp/server.py` (the `FastMCP` app;
`fastmcp/server/server.py:287` in the venv is the class - read its tool
registration and HTTP mounting surface before writing any code),
`pathfinder/mcp/tools/` (one module per group: `catalog.py`, `records.py`,
`steps.py`, `evidence.py`), `pathfinder/mcp/schemas.py` (typed
result models where D's tools do not already return one). Contract 7 source
list gains `veupathdb_mcp` (`apps/api/pyproject.toml:333-339`) and a new
forbidden edge: `veupathdb_mcp` never imports `pathfinder.ai` or
`pathfinder.transport` (new import-linter contract in the same block).

**Per-tool requirements (the brief's checklist, one row per tool of section
1.4):** explicit `site_id: str` argument validated against the known site
list; `inputSchema` from the function signature (fastmcp derives it - verify
how it renders `list[str]` and unions before relying); explicit
`annotations` exactly as the section 1.4/design 3.1 table says (every tool
declares `readOnlyHint` explicitly - absent is a conformance failure per
family 3); `outputSchema` + `structuredContent` for every tool with a typed
result; tool-level `_meta` `org.veupathdb.assistant/streamPart` ONLY where a
part kind will exist (start with none or one - e.g.
`data-wdk.enrichment-results` on `enrich_gene_ids` - and record which);
errors as `isError: true` tool errors that NAME the offending field (family
4: the consuming default converts tool errors into `ModelRetry`,
`pydantic_ai/mcp.py:1562-1576`, so a vague error buys a wasted model turn).
Credential wiring per tool row (service-account for catalog, user token for
step reads and writers) through C2's dependency.

**Tests first.** In-process (no network): `tools/list` matches the sixteen
names + annotations table exactly (a table test - this is the inventory
pin); one call test per group against WDK fixtures; `run_control_tests_on_search`
declares `readOnlyHint: false, destructiveHint: false`; every tool's
description non-empty; every `inputSchema` an object schema.

**Verify.** Ladder P, baselines first; ladder K (backlog: none closed here;
knowledge: a `docs/knowledge/decisions/` entry for "the wdk-mcp server is a
product module served from the api image", naming the rejected standalone
package).

**Traps.** Do not import the `ai/tools/standalone` wrappers - the server
calls `services/` (C1's halves); importing the wrappers would drag
`RunContext`/`AgentDeps` and the gate into a stateless server.
`get_step_sample_records` needs `record_type` as an argument (section 1.4);
do not guess it from a session that does not exist here. Site list: reuse
`services/catalog/sites.py:list_sites` (the site_help agent already does,
`assistants/site_help/agent.py:74-79`).

#### D2. Entrypoint, container, compose, and the memory ceilings

**Why.** The server runs as its own container on the api image (section 1.2)
so its per-site catalogs and semantic indexes live in one process with a
ceiling; and the same change lands `mem_limit`s for worker and the new
service, which is the uncontroversial half of the worker-memory backlog item
(the kill must land on the process that grew, not on the api).

**Files.** `apps/api/src/pathfinder/mcp/__main__.py`
(`python -m veupathdb_mcp`, uvicorn serving the FastMCP HTTP app + a
`/health` route); `docker-compose.yml`: new `wdk-mcp` service (api image,
own port, `mem_limit`, healthcheck) and `mem_limit` on `worker` (the
measured appetite: worker hit 5.26 GiB while api needs ~5-6 GiB warm on an
11.42 GiB VM - pick ceilings that sum under the VM with headroom and record
them in the compose comments? NO - compose comments are config narration;
record the numbers in the task report and the knowledge item instead);
quadlet parity if `quadlets/` carries the worker (check
`quadlets/pathfinder-worker.container`).

**Tests first.** A compose-config assertion test is not meaningful in pytest;
the verification IS the docker ladder: build, force-recreate, `docker compose
ps` healthy, `curl` the health route, one MCP `initialize` +
`tools/list` from a host-side script, `docker stats --no-stream` recorded
before/after a catalog call on two sites showing growth lands in `wdk-mcp`.
The worker-memory backlog item stays OPEN (its eviction half is batch F /
decision point 4) - EDIT the item in the same change to strike the
now-landed ceiling half and name what remains, rather than deleting it.

**Verify.** Docker ladder + ladder K. The DOCKER_CONFIG credential-helper
bypass applies to this machine's builds (section 4.0).

**Traps.** `api depends_on worker` exists (`docker-compose.yml:11` region) -
the new service must not join that dependency chain (chat must not wait on
wdk-mcp). Do not publish the DB port further or weaken anything in compose
while touching it. Memory: fastembed loads per process - the new container
pays the model once; confirm the api's own warmup behaviour is unchanged
(`/health/live` slowness is a known trait).

#### D3. Live proof: a real client against the served endpoint

**Why.** The design doc's P2 exit is "Claude Code can call it" and the
critical auth case is two-user isolation - user A's token cannot read user
B's step through ANY tool that names one (family 2, the case the tenancy
work proved necessary). This task is the served server's first hostile
consumer.

**Files.** `apps/api/src/pathfinder/tests/integration/mcp/test_served_wdk_mcp.py`
(marked - requires the compose stack + `WDK_TEST_TOKEN`; skips cleanly
without, mirroring the live-lane pattern `verification-gates.md:38`): a
pydantic-ai `MCPToolset("http://localhost:<port>/mcp", ...)` client (the URL
transport path, `pydantic_ai/mcp.py:1470-1516`), driving: `tools/list`
stability across two connections (family 6); a catalog read with no user
token (service mode); `get_step_estimated_size` with user A's token against
a step of user B -> protocol-level refusal, never data (build the two
identities from `WDK_TEST_TOKEN` + a second credentialed account if the
harness has one; if only one registered account exists, the isolation case
uses a fabricated foreign step id and asserts the refusal shape, and the
task report says so explicitly - do not silently narrow the claim);
`run_control_tests_on_search` end to end on plasmodb with 2-3 known control
genes and teardown of the temporary strategy (the live-lane rule: every
resource a live check creates is deleted,
`verification-gates.md:38`).

**Verify.** Docker ladder first (stack up), then the marked test file green;
ladder P unaffected (the file skips in the default run - assert that too).

**Traps.** The WDK test account carries e2e debris (hundreds of strategies -
status addendum); never assert on account-global counts, always on resources
the test created. Timeouts: `init_timeout` 5 s default
(`pydantic_ai/mcp.py:955-956`) - the server's cold start must beat it or
declare otherwise; measure and record.

---

### Batch E - the conformance suite as a package

Adversarial review focus: run the suite yourself against (a) our served
server - green; (b) a deliberately broken fixture server the suite ships for
its own tests (wrong annotation, missing outputSchema, credential echoed in
an error) - each family catches its planted defect. A suite that cannot fail
is not a gate.

#### E1. Package skeleton + families 1, 4, 6

**Why.** A server is admitted when a human reads a passing conformance
report (design doc 4.2); the suite must be runnable by a Java team on its
own CI, which means: a pip-installable pytest plugin, configured by URL +
credential, importing nothing of ours.

**Files (new).** `assistant-platform/packages/mcp-conformance/pyproject.toml` (name
`veupathdb-mcp-conformance`, deps: `mcp`, `httpx`, `pytest`, `pydantic`;
NO pathfinder, NO assistant_core - boundary test included, modeled on
`assistant-core/tests/unit/test_package_boundary.py`), `src/mcp_conformance/`
(plugin module: `--mcp-endpoint`, `--mcp-bearer`, `--mcp-report` options;
report writer producing the admission-report JSON), families as test
modules: `test_shape.py` (family 1: initialize negotiates a revision and the
report names it; unique prefix-safe names; non-empty descriptions; object
inputSchemas; streamPart-declaring tools also declare outputSchema),
`test_errors.py` (family 4: bad argument -> tool error naming the field,
never transport error; failing tool -> `isError` with actionable content),
`test_stability.py` (family 6: `tools/list` identical across two fresh
connections). Ladder C defined here (`ruff`, `mypy --strict`, `pytest` of
the suite's OWN unit tests against its bundled fixture servers).

**Tests first.** The suite's own tests: an in-process compliant fixture
server passes each family; a planted-defect server fails with the defect
named. (The suite is itself TDD'd against its fixtures.)

**Verify.** Ladder C; ladder K (knowledge: a decision entry naming why the
suite is a separate distribution).

**Traps.** Protocol revision: pin assertions to 2025-11-25 semantics but
accept the negotiated-version mechanism (`mcp/types.py`
`LATEST_PROTOCOL_VERSION`; `DEFAULT_NEGOTIATED_VERSION` is older - design
doc Appendix A); the report NAMES the negotiated revision rather than
failing on it. Python version floor: a foreign team runs this - target the
oldest Python the `mcp` package supports, not 3.14 idioms (no PEP 758
multi-except syntax here; it must run where they run it).

#### E2. Families 2, 3, 5 (auth, annotations, timeouts)

**Why.** These are the falsifiable halves of trust: credentials refused as
protocol errors and never echoed; `readOnlyHint` proven by calling twice
against a fixture account and diffing; a call past the budget times out with
the turn surviving. Family 3's account comparison is what makes an
annotation more than a promise.

**Files.** `src/mcp_conformance/test_auth.py` (no credential -> protocol
error; wrong credential -> same; 401 carries `WWW-Authenticate` with
`resource_metadata`; no credential substring in any result/error; two-user
isolation when the runner provides `--mcp-bearer-second`),
`test_annotations.py` (every tool declares `readOnlyHint` explicitly -
absent FAILS; `readOnlyHint: true` called twice, account state compared via
a provider hook the runner supplies - the hook is an extension point because
"account state" is server-domain-specific; `idempotentHint: true` -> two
calls, equal results), `test_timeouts.py` (a `--mcp-slow-tool` named by the
runner is driven past `--mcp-max-call-seconds` and the client-side timeout
fires cleanly).

**Tests first.** Same fixture-server pattern: a compliant and a planted-
defect server per family.

**Verify.** Ladder C.

**Traps.** The account-comparison hook must not require our WDK client - it
is a callable the operator's harness provides; for OUR server, E3 supplies a
WDK-backed hook that lives in `apps/api` tests, not in the suite.

#### E3. Green against our server + nightly lane

**Why.** The suite's first admission report is our own server's (P2 exit:
"the conformance suite is a package a foreign team can run, and it is green
against our own server"); and admitted sources re-run nightly, quarantining
on failure rather than blocking PRs (design doc 4.2, mirroring the WDK live
lane and the eval-promotion policy).

**Files.** `apps/api/src/pathfinder/tests/integration/mcp/test_conformance_ours.py`
(marked; composes the suite programmatically against the compose-served
endpoint with the WDK-backed account hook and both credentials);
`.github/workflows/mcp-nightly.yml` modeled on `wdk-nightly.yml` (schedule,
skip-without-credentials, files an issue on failure); the admission report
of our server checked in under `docs/knowledge/` as data? NO - reports are
run artifacts, not knowledge; store the report shape's example in the
package's README and leave real reports to CI artifacts.

**Verify.** Docker ladder (stack up) + the marked test green + ladder C + K.

**Traps.** Enrichment field names are a conformance case here (design doc
3.1 note): the case asserts `goId`/`goTerm`, `pathwayId`/`pathwayName`,
`word`+`pathwayName` under `resultData` - C3's test moves up into suite
form. Nightly must not run against public VEuPathDB sites beyond what the
WDK nightly already does; it targets OUR served container in CI compose.

---

### Batch F - packages publish alone, protocol debt paid

Adversarial review focus: build both packages from clean checkouts of their
directories (`uv build` / `yarn pack` equivalents) and install the artifacts
into a scratch venv/project; import `assistant_core` and instantiate the
client with ZERO path dependencies present. Then replay the failed-turn
nine-chunk log through both reducers and see the third part.

#### F1. assistant-core sheds `pathfinder-shared`

**Why.** The runtime cannot be a second consumer's dependency while it
path-depends on `pathfinder-shared` (`assistant-platform/packages/assistant-core/pyproject.toml:19,22-23`);
the two modules it actually uses are runtime-part payloads that belong in
the package (section 1.3). After this task the package builds alone.

**Files.** MOVE `packages/shared-py/src/shared_py/stream_parts/background_task.py`
and `turn_usage.py` into
`assistant-platform/packages/assistant-core/src/assistant_core/conversation/stream_parts/`
(as `task_parts.py` and `turn_usage.py`, or one module - keep names
`TaskProgress`, `TaskCompleted`, `TurnUsage` unchanged: they are wire-adjacent
and PROTOCOL-named); update the two package importers
(`graph/stream_events.py:11`, `conversation/stream_parts/core_parts.py:3-8`);
DELETE the originals from shared-py and migrate every `apps/api` importer of
those two modules (grep `shared_py.stream_parts.background_task\|shared_py.stream_parts.turn_usage`
across apps/ and packages/ - as of this writing the only importers are the
two package files and the boundary test, but re-grep at execution time);
`assistant-platform/packages/assistant-core/pyproject.toml` drops `pathfinder-shared` and its
uv source; `tests/unit/test_package_boundary.py:24-25` drops the shared_py
allowance entirely (the allowed-import set shrinks - the test gets STRICTER);
`apps/api/pyproject.toml` keeps its own `pathfinder-shared` dep for the
product parts (untouched).

**Tests first.** The boundary test tightened (no `shared_py` import allowed) -
RED until the move lands; `uv build` in the package directory produces a
wheel; a scratch-venv install + `import assistant_core` smoke (scripted in
the task, run via the scratchpad, not committed as a test).

**Verify.** Ladders R and P (the api resolves the models from their new
home), baselines first; ladder K (decision entry: runtime part payloads live
in the runtime; the alternative - publish pathfinder-shared too - named and
rejected as a second package with no second consumer).

**Traps.** No re-export shims in shared_py (the no-backwards-compat rule);
every importer moves in this task. Alembic/OpenAPI untouched (these models
are not tables and the schema index reads the registry, which follows the
import move transparently - verify `core_parts.py` still registers the same
kinds by running the OpenAPI dump only if ladder P's tests do not already
pin it).

#### F2. assistant-client-ts builds and packs

**Why.** The client's `exports` point at `./src/*.ts`
(`assistant-platform/packages/assistant-client-ts/package.json`), which only a TypeScript
consumer inside this repo can use; a VEuPathDB host needs a packed artifact
with JS + d.ts. The three-ring shape and the zero-dependency core are
load-bearing and must survive the build
(`docs/knowledge/decisions/the-client-is-a-package-with-three-rings.md`).

**Files.** `assistant-platform/packages/assistant-client-ts/`: `tsconfig.build.json` (declaration
emit to `dist/`), package.json `exports` for the three entries mapping to
`dist/` (types + import conditions), `files: ["dist"]`, a `build` script,
`prepack` wiring; `apps/web`'s consumption must keep working (it resolves
the workspace package - confirm whether it consumes src or dist and keep the
repo-internal path working without a dual-condition hack; if the workspace
consumes `src` via TS paths, keep that and let `exports` govern the packed
artifact only - record which).

**Tests first.** Ladder T stays green; a `yarn pack` + install-into-scratch
smoke (scripted): `import { AssistantClient } from "@pathfinder/assistant-client"`
resolves in a plain Node + TS project with `ai` NOT installed (peer stays
optional, `package.json` `peerDependenciesMeta`), and importing the ai-sdk
ring without `ai` fails with the package-manager's peer message, not a
runtime crash.

**Verify.** Ladder T; ladder W (the app still compiles); ladder K.

**Traps.** The core ring must stay dependency-free at RUNTIME - the build
may not introduce a helpers dependency (`tsc` `importHelpers` off). The
conformance suite reads `PROTOCOL.md` via `scripts/sync-protocol.mjs`
(`package.json` `sync:protocol`) - packing must not break the sync gate's
relative path assumptions; run `yarn sync:protocol` and the suite after.

#### F3. A failed turn stays visible after reload (closes `failed-turn-shows-no-error-after-reload.md`, PROTOCOL 1.3.0)

**Why.** A turn that dies mid-answer renders "Response failed" live but
NOTHING after a reload, because no reducer maps the `error` chunk to a part
(the backlog item's measured nine-chunk log reduces to two parts on both
sides); a reader mistakes a truncated answer for a finished one. The fix is
the backlog item's option 1: a durable part, because the AI SDK owns the
`error` chunk shape and has no error part type.

**Files.** `assistant_core/graph/stream_events.py`: `TurnFailedPayload`
(fields: `errorText: str`) + `turn_failed_event(...)` beside
`turn_stopped_event`; register `data-turn-failed` in
`conversation/stream_parts/core_parts.py`; emit it wherever an `ErrorChunk`
is written today: `apps/api/.../turn_runner.py:295-301` (`_drive_graph`'s
except arm) and the stalled-turn closer (`jobs/maintenance.py`, find
`_close_stalled_turn`); PROTOCOL.md: the part row in section 5.2, a
changelog row 1.3.0, and the section 6 sentence tying it to the `error`
chunk (additive only); client-ts `yarn sync:protocol` + regenerated capture;
web renderer `features/conversation/content/parts/` + registration in
`contentComponents.ts`; `yarn generate:types` if the payload model changes
the OpenAPI schema index (it does - the registry feeds it; requires the api
container running).

**Tests first.** Backend: the nine-chunk replay from the backlog item -
extend `tests/_support/chunk_log.py`-driven reduction test to assert a THIRD
part (`data-turn-failed`) present after the fix (the part is durable so the
reducers need no new rule - that is the point of option 1; the test proves
it). Package: `test_protocol_document.py` captures the new part (it fails on
undocumented kinds - the PROTOCOL edit and the capture regeneration are one
change). Client: conformance suite regenerated (`sync:protocol` bites, then
green). Web: snapshot-replay vitest asserting the renderer receives the
part.

**Verify.** Ladders R, P, T, W; ladder K (backlog file + index line
deleted). Docker rebuild if manual verification through the UI is performed
(worker emits the chunk).

**Traps.** `finishReason` stays `"error"` where it already is - the part is
IN ADDITION, and PROTOCOL 6's rule ("A client MUST use the error chunk, not
finishReason") gains the part as the durable footprint; wording additive.
The stalled-turn sweep writes from the WORKER - rebuild + force-recreate
before any manual check. Version bump discipline: PROTOCOL minor 1.3.0, one
changelog row, `assistant-platform/packages/assistant-client-ts` version minor-bumps with it.

#### F4. The task card reads the thread (closes `web-still-reads-the-per-task-sse-dialect.md`)

**Why.** The thread carries the whole durable-task lifecycle since 1.1.0
(PROTOCOL 6.1) and the reducer already reconciles progress onto the message
(`data-task-progress` carries the task id as its `id` - PROTOCOL:233-236),
yet the card still opens a second SSE connection per task through the
deprecated dialect; a page with three tasks holds four streams. One
connection, one parser, one reconnect rule.

**Files.** `apps/web/src/features/conversation/content/parts/DataBackgroundTaskStarted.tsx`
re-rendered from the message's own parts (`data-background-task-started`
opens, reconciled `data-task-progress` drives the bar,
`data-task-completed` closes and fires the resume it announces today - port
that trigger from `taskCompletionResume.ts` semantics); DELETE
`useTaskEventStream.ts`, `taskLiveState.ts`, `taskCompletionResume.ts` and
their test files; `lib/sse/typedEventStream.ts` and the client `./legacy`
ring STAY (sole remaining consumer: `features/workbench/api/streaming.ts`,
the experiment/sweep streams, which are not thread events - the backlog
item's own carve-out). The per-task HTTP route stays byte-for-byte
(`docs/knowledge/decisions/durable-task-progress-belongs-in-the-thread-log.md`).

**Progress granularity decision (the backlog item demands it be decided, not
skipped):** the log coalesces at 5 percentage points / 10 seconds
(PROTOCOL:242-248). DECIDE by looking: run one mock durable task in the dev
stack and watch the bar. Recommendation to adopt unless it visibly reads as
stalled: coarse steps are acceptable for a card whose states are
started/working/done; if it reads as stalled, keep the per-task subscription
FOR THE BAR ONLY (the item's fallback) and say so in the report - the other
three deletions still stand.

**Tests first.** Vitest: a reduced message containing the three part kinds
renders the card through its full lifecycle with NO network (jsdom, no
EventSource); the resume fires exactly once on `data-task-completed`; a
reloaded snapshot (parts only, no live stream) renders the finished card.
E2E: one existing durable-task journey spec updated, run standalone (the
full suite is out of scope; the e2e-residuals backlog item documents suite
contention).

**Verify.** Ladders W and T (the client package is untouched but its
consumer changed - run both); ladder K (backlog file + index line deleted;
the decision paragraph lands in the report and, if the fallback was taken,
the item is EDITED to its residual instead of deleted).

**Traps.** React Compiler project: no `useMemo`/`useCallback`/`memo`, and
`useEffect` is banned by standing feedback - the card must derive from
props/parts, and the one legitimate effect (firing the resume POST) must go
through the existing chat-helpers action path, not a raw effect; find how
`consultActions.ts` fires and mirror it. `check-boundaries.mjs` runs in
ladder W - deleting files can strand an exception entry in its config;
clean it in the same change.

---

### Batch G - second-consumer proof

Adversarial review focus: drive the pilot turn from a cold stack yourself
(fresh compose up), read the chunk log end to end, and verify the MCP tool's
approval card round-trips from the browser UI - then kill the wdk-mcp
container mid-turn and confirm the turn degrades per the `required=False`
path instead of hanging.

#### G1. A pilot assistant consumes wdk-mcp through the declaration path

**Why.** The program's claim is that an assistant declares a tool source and
the runtime does the rest; the only honest proof is an assistant that is not
PathFinder answering a real turn with tools served over the network by our
own server, approval included - the in-repo half of the design doc's P4,
runnable before any VEuPathDB decision.

**Files.** `apps/api/src/pathfinder/assistants/site_help/spec.py` +
`agent.py`: site_help declares `tool_sources=(ToolSourceDeclaration(name="wdk", source_id="veupathdb-wdk-mcp", tools=frozenset({"list_record_types", "search_for_searches", "run_control_tests_on_search"}), required=False),)`
and its `build_turn_context` hands `request.tool_sources` to the agent
factory (thread through `build_graph`'s `build_agent` closure - the factory
takes the resolved toolsets as an argument now; keep the zero-source path
identical). Dev admission config: the `wdk-mcp` compose endpoint admitted
with `credential_mode: "service"` for the catalog pair and the approval
predicate doing the rest (`run_control_tests_on_search` has
`readOnlyHint: false` so it asks - no per-assistant always_approve needed).
Mock story: the mock provider swaps the model, not the tools
(`site_help/agent.py:95-99`) - the mock journey must script a turn that
calls `list_record_types` through the REAL local server (docker) with the
scripted model; if the e2e mock cannot reach docker in CI, the CI variant
uses the in-process FastMCP server via a test-only admission record, and
the report says which ran where. `devtools/chat` must print MCP-sourced
tool calls legibly (extend only if the run artifacts are unreadable -
check first).

**Tests first.** Integration (compose-marked): a site_help turn whose chunk
log shows `tool-wdk_list_record_types` input/output (the prefix proves the
`PrefixedToolset` layer); a turn calling the writer stops at
`tool-approval-request` and the next POST's approval resumes it (PROTOCOL
6.2 shape, already exercised by the runtime suite - this test pins it over
a NETWORK source). Unit: the spec's declaration tuple pinned.

**Verify.** Ladders P and W; docker ladder; one browser pass through the
approval card (manual, screenshotted into the task report). Ladder K.

**Traps.** Worker runs the turn: the worker container must reach
`wdk-mcp` by service name over the compose network - add it to the
worker's environment/urls the same way WDK base URLs travel; NEVER via
localhost. The identity gate: site_help declares none
(`site_help/spec.py:78-85`) - the service-mode catalog tools are exactly
why it can stay that way; do not add a WDK login gate to the pilot.

#### G2. Program reconciliation

**Why.** The knowledge bundle must end the program telling the truth: closed
items gone, open items accurate, decisions recorded, and the assessment's
status addendum extended so the next planner does not re-litigate what
landed (the update-docs-every-time rule is per-change; this task is the
final sweep that checks nothing slipped).

**Files.** `docs/knowledge/backlog/index.md` reconciled against the six
items this program touched (A1, A2, A3, F3, F4 deleted; worker-memory
edited to its residual or deleted if F's eviction landed);
`docs/assessment/2026-08-17-veupathdb-assistant-platform-assessment.md`
status addendum: a dated entry for the program (WS4 in-repo half landed;
what remains is theirs + the asks);
`docs/design/2026-08-23-mcp-and-sdk-program.md`: a short dated closure note
at the top of section 8 pointing here (matching the pattern its section 6.4
already uses), NOT a rewrite. Ladder K.

**Verify.** Ladder K; a grep that no `backlog/` file is referenced by
`index.md` without existing and vice versa (the gate script checks this -
run it and read the output).

---

## 5. Decision points for the owner

None of these blocks batches A-C; D2's container shape (point 3) is the
earliest one that bites, and its recommendation is safe to proceed on.

1. **The VEuPathDB asks (design doc section 7, Asks 1-8).** Not restated
   here; they gate the JOINT phases (their server, the real pilot placement,
   `veupathdb_user` sign-off), not this plan's batches. Recommendation:
   schedule the meeting after batch D, when a served server and a green
   conformance report exist to demonstrate - the asks land better with the
   artifact on screen. Batches A-G proceed regardless; `veupathdb_user`
   mode ships implemented but is refused unless an admission record names
   it, so the deviation stays paper until they sign (design doc 2.4).
2. **Publish target for the three packages.** Options: PyPI / GitHub
   Packages / git-tag consumption. Recommendation: GitHub Packages under the
   VEuPathDB org for `veupathdb-mcp-conformance` (their `lib-jaxrs` idiom -
   assessment 1.3 - and the suite's audience is their CI), decision deferred
   for `assistant-core` and the TS client until the second consumer is named;
   F1/F2 produce pack-and-install proofs either way, so nothing waits.
3. **wdk-mcp hosting shape.** Own container on the api image (recommended:
   memory isolation - the OOM history is real - independent restart, and
   VEuPathDB container-per-service parity) vs a mounted route on the api
   app (rejected: couples the api's memory to per-site indexes again) vs a
   standalone distribution (rejected: it imports `pathfinder.services`;
   section 1.2). D2 proceeds on the recommendation.
4. **Index placement and the worker's memory (intersects
   `worker-memory-grows-unbounded-with-sites-touched.md`).** The backlog item
   offers eviction OR "the worker never builds indexes, the api serves
   semantic queries", attributing the latter to the design doc - the design
   doc never says it (correction 3, top of this document). The real fork:
   (a) LRU eviction of per-site indexes over a budget, in-process, worker
   keeps building; (b) PathFinder's own retrieval tools call the wdk-mcp
   server over HTTP (the design doc's "thin local wrapper that calls the
   MCP tool", section 3.1), moving every index into the one wdk-mcp
   container. Recommendation: D2's ceilings now, (a) as a small follow-up
   task appended to batch F, and (b) deferred until the pilot proves the
   server under load - a network hop inside FRAME's hottest loop
   (`search_for_searches` in `toolsets/frame.py:57-78`) is a latency and
   availability bet that should not ride the same program that builds the
   server. If the owner picks (b) now, it replaces the F follow-up and adds
   ~1 EW.
5. **`enrich_gene_ids` in v1.** Recommendation: ship it (batch C3/D1) - it
   is the evidence-group tool that makes the server compelling to a
   gene-page assistant, and its field-name conformance case (WDK-ANS-007)
   is the suite's best teeth. Dropping it saves ~0.5 EW and drops the
   sixteenth tool to fifteen.
6. **Second consumer for the pilot.** The design doc argues the gene-page
   assistant (Ask 2); in-repo, G1 uses site_help as the stand-in.
   Recommendation: keep site_help as the proof vehicle and build the real
   gene-page assistant only after Ask 2 is answered - a second demo
   assistant nobody ships is scope creep.
7. **Conformance fixture credentials.** Family 2/3 need a fixture account
   (and ideally a second) - today the harness has `WDK_TEST_TOKEN` /
   `WDK_TEST_EMAIL`/`WDK_TEST_PASSWORD`. Owner call: whether to provision a
   second registered account for the two-user isolation case (recommended -
   D3 otherwise proves only the refusal shape) and whether a service-account
   key for a non-PathFinder host exists (that is Ask 1 verbatim).

## 6. Non-goals

- **The reference Java server** (design doc section 5) and anything a
  VEuPathDB team deploys - theirs, supported by our conformance suite.
- **Bridging MCP task-augmented execution to `@durable_tool`** - v2 question,
  named refusal in design doc 2.6/Ask 8; the suite's family 5 enforces the
  budget instead.
- **A React-18 component package for web-monorepo** - assessment ranked it
  last; the headless client is the offer.
- **The model gateway (assessment WS5), per-application budgets (Appendix C
  row 5), SSE fan-out via NotifyDispatcher (row 8)** - hardening tracks with
  their own ranking, not tool-boundary work.
- **Exposing `web_search`/`literature_search` or the memory store over MCP** -
  refused in design doc 3.2 (paid proxy; cross-assistant memory reads).
- **Routing PathFinder's own FRAME retrieval through the network MCP server**
  - decision point 4(b), explicitly deferred.
- **Guest/anonymous WDK access** - `wdk-requires-registered-login.md` stands;
  Ask 1 is VEuPathDB's to answer.
- **Rewriting the per-task SSE route** - it stays byte-for-byte per its
  decision; only the web app's use of it ends (F4).

## 7. Sizing and sequencing

| Batch | Estimate | May start when | Stack needed |
|---|---|---|---|
| A | 1-1.5 EW | now | none (ladders only) |
| B | 1.5-2 EW | after A (B4 after A1's toolset edits settle; B1-B3 after A2's approvals edits settle) | none |
| C | 1 EW | now (parallel with A/B; different layers) | none; live-marked tests optional |
| D | 1.5 EW | after B and C | dev docker |
| E | 1-1.5 EW | E1/E2 parallel with C/D; E3 after D | E3: dev docker |
| F | 1-1.5 EW (+0.5 if decision 4(a) lands here) | F1/F2 now; F3 after A (protocol discipline, no code dependency); F4 any time | F3/F4 manual checks: dev docker |
| G | 0.5-1 EW | after D (and F3 for a clean demo) | dev docker |

**Total: roughly 8-10 EW.** Reconciliation with the design doc's totals: its
P1+P2 was 2.5-3.5 EW; this plan additionally carries the trust-base debt
(batch A), the sub-agent flip it named but did not price separately (B4),
the SDK packaging work its section 6 assumed away (F1/F2), two protocol
debts (F3/F4), the conformance suite priced as a real handover package
(E, the thing it said was priced thin at 2-3 total), and the second-consumer
proof (G). The numbers are consistent once those are added back.

**Critical path:** A2 -> B1/B2/B3 -> D1 -> D3 -> G1. Everything else
parallelizes around it.

**Machine reality.** One 11.42 GiB Docker VM; api warm ~5-6 GiB; the worker
has reached 5.26 GiB. Batches A/B/C/E1/E2/F1/F2 run on ladders alone (the
assistant-core suite starts one pgvector testcontainer) and can run while
the dev stack is DOWN. D2/D3/E3/G need the dev stack UP - schedule them so
no full e2e Playwright run shares the VM with them, and expect D2's ceilings
to make any accidental overlap fail loudly on the right container, which is
the point. Builds are slow and the credential-helper bypass applies; batch
agents budget for one rebuild + force-recreate cycle per docker-touching
task, not per edit.
