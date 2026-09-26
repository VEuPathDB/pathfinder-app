# User acceptance testing

The exit criteria, the sites and accounts, and the scripted flows a UAT runner
follows on the test deployment. Every expected number names the site, the
site's build (71) and the day it was measured (2026-09-24). Labels are quoted as
the code rendered them that day; the code moves, so a label that differs on a
step is checked against the current source before it is filed.

## Documents

- [Exit criteria](exit-criteria.md) - what "UAT passed" means: severities, the pass rule, what to record, count drift, the stop rule
- [Sites and accounts](sites-and-accounts.md) - the five sites and why, build numbers, baseline counts, what a runner needs, the cleanup of each flow
- [Runner checklist](runner-checklist.md) - the order of one sitting with measured times, the hygiene sweep `H1`, the bug template
- [Known limits](known-limits.md) - what is decided or on the backlog and is not a bug
- [Findings](findings.md) - defects measured while writing these flows; fixed before UAT starts
- [First run and navigation](flows-first-run.md) - `F1` to `F12`
- [Building strategies, standard](flows-strategy-standard.md) - `S1` to `S16`
- [Building strategies, non-standard and exceptions](flows-strategy-exceptions.md) - `N1` to `N13`
- [Verification and evidence](flows-verification.md) - `V1` to `V7`
- [Studies (EDA)](flows-eda.md) - `E1` to `E8`
- [Memory and notes](flows-memory-notes.md) - `M1` to `M6`
- [Composer](flows-composer.md) - `C1` to `C16`
- [Settings and account](flows-settings-account.md) - `A1` to `A7`
- [Gene sets and exports](flows-gene-sets-exports.md) - `G1` to `G4`
- [Cross-site and orthology](flows-cross-site.md) - `X1` to `X6`
- [Resilience](flows-resilience.md) - `R1` to `R8`
- [Deployment checks](flows-deployment.md) - `D1` to `D11`
- [Layout and access](flows-layout-access.md) - `L1` to `L5`

## Exit criteria in ten lines

1. Deployment checks `D1` to `D11` pass once; a failure stops the run.
2. Every core flow passes on every site it names, with zero blockers and zero majors.
3. Every other flow passes, or ends on its expected refusal (code text word for word, model text by its facts).
4. At most 3 open minors per site and 10 across the run, after merging duplicates.
5. A blocker stops that site's run; the same blocker on two sites stops the run.
6. Counts are compared on the recorded build; a new build tolerates max(5 genes, 10 %).
7. A count off the tolerance is re-measured on the site; the app disagreeing with the site is a blocker.
8. A different step layout is a failure on any build.
9. Account B never sees account A's data (`F12`); a leak is a blocker.
10. `H1` leaves both accounts empty, and every finding is fixed or moved to known limits in writing.

## Build numbers at UAT start

| Site | Recorded | At UAT start | Date |
|---|---|---|---|
| veupathdb | 71 | | |
| plasmodb | 71 | | |
| vectorbase | 71 | | |
| toxodb | 71 | | |
| fungidb | 71 | | |

## Tally

Result: `pass`, `fail`, `blocked` or `re-measure`. Bug ids: the tracker's, comma-separated.

| Flow | Site | Result | Bug ids |
|---|---|---|---|
| D1 to D11 | deployment | | |
| F1 | veupathdb | | |
| F1 | plasmodb | | |
| F1 | vectorbase | | |
| F1 | toxodb | | |
| F1 | fungidb | | |
| F2 | each site | | |
| F3 | one site | | |
| F4 | each site | | |
| F5 | each site | | |
| F6 | each site | | |
| F7 | each site | | |
| F8, F9, F10, F11 | plasmodb | | |
| F12 | plasmodb | | |
| S1 | veupathdb | | |
| S1 | plasmodb | | |
| S1 | vectorbase | | |
| S1 | toxodb | | |
| S1 | fungidb | | |
| S2 | veupathdb | | |
| S2 | plasmodb | | |
| S2 | vectorbase | | |
| S2 | toxodb | | |
| S2 | fungidb | | |
| S5 | plasmodb | | |
| S5 as X3 | vectorbase | | |
| S5 as X3 | toxodb | | |
| S5 as X4 | fungidb | | |
| S5 as X5 | veupathdb | | |
| S3, S4, S6, S7, S8 | plasmodb | | |
| S9 to S16 | plasmodb | | |
| N1 to N13 | plasmodb (N9, N12 as stated) | | |
| V1 | each site | | |
| V2 to V7 | plasmodb | | |
| E1 to E8 | plasmodb | | |
| M1 to M6 | plasmodb | | |
| C1 to C16 | plasmodb | | |
| A1 to A7 | once | | |
| G1 | each site | | |
| G2 to G4 | plasmodb | | |
| X1 | plasmodb and vectorbase | | |
| X2 | each component site | | |
| X6 | vectorbase and plasmodb | | |
| R1 to R8 | once | | |
| L1 to L5 | once | | |
| H1 | both accounts | | |

## Flows under test

Where each flow runs without a runner. The e2e spec drives the flow on the mock stack (only the model is mocked; `@turn` tests run once per site in `E2E_SITES`, plasmodb and vectorbase in CI). The model check runs the flow on the real model before a release, from a machine that holds the key, against the recorded expectation. The fault spec plays a wrong model and asserts the guard that corrects it. `none` names why a flow stays with the runner; `-` in the model-check column marks a flow whose expectation is not a model decision, and in the fault column a flow with no guard of its own; every fault test is in `apps/web/e2e/uat/faults.spec.ts`.

| Flow | e2e spec | model check | fault spec |
|---|---|---|---|
| F1 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F2 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F3 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F4 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F5 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F6 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F7 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F8 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F9 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F10 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F11 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| F12 | `apps/web/e2e/uat/first-run.spec.ts`; step 8 needs a second VEuPathDB account | - | - |
| S1 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s1-{plasmodb,vectorbase,toxodb,fungidb,veupathdb}` | `transcript-count`, `misstated-count`, `unlisted-search`, `value-as-term`, `off-vocabulary` |
| S2 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s2-{plasmodb,vectorbase,toxodb,fungidb,veupathdb}` | `long-reason` |
| S3 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s3-plasmodb` | - |
| S4 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s4-plasmodb` | - |
| S5 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s5-{plasmodb,vectorbase,toxodb,fungidb,veupathdb}` | - |
| S6 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s6-plasmodb` | - |
| S7 | `apps/web/e2e/uat/strategy-standard.spec.ts` | - | - |
| S8 | `apps/web/e2e/uat/strategy-standard.spec.ts` | - | - |
| S9 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s9-plasmodb` | - |
| S10 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s10-plasmodb` | - |
| S11 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s11-plasmodb` | - |
| S12 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s12-plasmodb` | - |
| S13 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s13-plasmodb` | - |
| S14 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s14-plasmodb` | - |
| S15 | `apps/web/e2e/uat/strategy-standard.spec.ts` | `uat-s15-plasmodb` | - |
| S16 | `apps/web/e2e/uat/strategy-standard.spec.ts` | - | - |
| N1 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n1-plasmodb` | `short-card-reply` |
| N2 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n2-plasmodb` | - |
| N3 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n3-plasmodb` | the `cross-organism` arc (FND-4) |
| N4 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n4-plasmodb` | - |
| N5 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n5-plasmodb` | `misnamed-deletion` |
| N6 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | the `live_model` judge test in the same pre-release run | - |
| N7 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n7-plasmodb` | `short-card-reply` (FND-14, also seen here) |
| N8 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n8-plasmodb` | the `portal-only` arc (FND-12) |
| N9 | `apps/web/e2e/uat/strategy-exceptions.spec.ts`; step 2 on the mock stack holds that every stored step runs a search plasmodb lists; that plasmodb builds nothing is the model check's | `uat-s2-toxodb` (step 1), `uat-n9-plasmodb` (step 2) | - |
| N10 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n10-plasmodb` | - |
| N11 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n11-plasmodb` | - |
| N12 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n12-toxodb` | - |
| N13 | `apps/web/e2e/uat/strategy-exceptions.spec.ts` | `uat-n13-plasmodb` | - |
| V1 | `apps/web/e2e/uat/verification.spec.ts` | - | `all-unclear` |
| V2 | `apps/web/e2e/uat/verification.spec.ts` | `uat-v2-plasmodb` | `repeat-control-test`, `unbacked-controls` |
| V3 | `apps/web/e2e/uat/verification.spec.ts` | `uat-v3-plasmodb` | `sweep-without-controls` |
| V4 | `apps/web/e2e/uat/verification.spec.ts` | `uat-v4-plasmodb` | - |
| V5 | `apps/web/e2e/uat/verification.spec.ts` | `uat-v5-plasmodb` | - |
| V6 | none: the research tool source is not on the e2e stack | `uat-v6-plasmodb` | - |
| V7 | `apps/web/e2e/uat/verification.spec.ts` | `uat-v7-plasmodb` | - |
| E1 | `apps/web/e2e/uat/eda.spec.ts` | - | - |
| E2 | `apps/web/e2e/uat/eda.spec.ts` | `uat-e2-plasmodb` | `all-unclear` (FND-6, also seen here) |
| E3 | `apps/web/e2e/uat/eda.spec.ts` | - | - |
| E4 | `apps/web/e2e/uat/eda.spec.ts` | `uat-e4-plasmodb` | - |
| E5 | none: step 2 is an edit on the site's own page; steps 3 and 4 are `apps/web/e2e/feature/eda-read-only-tab.spec.ts`, route-mocked | - | - |
| E6 | none: a VDI upload installs on the site | - | - |
| E7 | none: needs the E6 upload | - | - |
| E8 | `apps/web/e2e/uat/eda.spec.ts` | `uat-e8-plasmodb` | the `eda-other-site` arc (FND-11) |
| M1 | `apps/web/e2e/uat/memory-notes.spec.ts` | - | - |
| M2 | `apps/web/e2e/uat/memory-notes.spec.ts` | - | - |
| M3 | `apps/web/e2e/uat/memory-notes.spec.ts` | - | - |
| M4 | `apps/web/e2e/uat/memory-notes.spec.ts` | - | - |
| M5 | `apps/web/e2e/uat/memory-notes.spec.ts` | - | - |
| M6 | `apps/web/e2e/uat/memory-notes.spec.ts` | `uat-m6-plasmodb` | - |
| C1 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C2 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C3 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C4 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C5 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C6 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C7 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C8 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C9 | `apps/web/e2e/uat/composer.spec.ts` | `uat-c9-plasmodb` | `short-card-reply` (FND-14, also seen here) |
| C10 | `apps/web/e2e/uat/composer.spec.ts` | `uat-c10-plasmodb` | - |
| C11 | `apps/web/e2e/uat/composer.spec.ts` | `uat-c11-plasmodb` | - |
| C12 | `apps/web/e2e/uat/composer.spec.ts` | `uat-c12-plasmodb` | - |
| C13 | `apps/web/e2e/uat/composer.spec.ts` | `uat-c13-plasmodb` | - |
| C14 | `apps/web/e2e/uat/composer.spec.ts` | `uat-c14-plasmodb` | - |
| C15 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| C16 | `apps/web/e2e/uat/composer.spec.ts` | - | - |
| A1 | `apps/web/e2e/uat/settings-account.spec.ts`; steps 2 to 4 need a real model | `uat-a1-plasmodb` (steps 2 to 4) | - |
| A2 | `apps/web/e2e/uat/settings-account.spec.ts`; step 1 only; the e2e stack runs with personal keys off | - | - |
| A3 | `apps/web/e2e/uat/settings-account.spec.ts` | - | - |
| A4 | `apps/web/e2e/uat/settings-account.spec.ts` | - | - |
| A5 | `apps/web/e2e/uat/settings-account.spec.ts` | - | - |
| A6 | `apps/web/e2e/uat/settings-account.spec.ts` | - | - |
| A7 | `apps/web/e2e/uat/settings-account.spec.ts` | - | - |
| G1 | `apps/web/e2e/uat/gene-sets-exports.spec.ts` | `uat-g1-plasmodb` | - |
| G2 | `apps/web/e2e/uat/gene-sets-exports.spec.ts` | - | - |
| G3 | `apps/web/e2e/uat/gene-sets-exports.spec.ts` | - | - |
| G4 | `apps/web/e2e/uat/gene-sets-exports.spec.ts` | - | - |
| X1 | `apps/web/e2e/uat/cross-site.spec.ts`; the mock stack holds that every stored step runs a search the site lists and that other sites' experiments are labelled and never bound; which experiment ranks first and whether plasmodb builds nothing are the model check's (the fake embedder ranks by name) | `uat-x1-vectorbase`, `uat-e8-plasmodb` (the plasmodb half) | - |
| X2 | `apps/web/e2e/uat/cross-site.spec.ts` | `uat-s2-{plasmodb,vectorbase,toxodb,fungidb}` | - |
| X3 | `apps/web/e2e/uat/cross-site.spec.ts` | `uat-s5-vectorbase`, `uat-s5-toxodb` | `all-unclear` (FND-6, also seen here) |
| X4 | `apps/web/e2e/uat/cross-site.spec.ts` | `uat-s5-fungidb` | - |
| X5 | `apps/web/e2e/uat/cross-site.spec.ts` | `uat-s5-veupathdb` (step 1), `uat-x5-veupathdb` (step 2) | `syntenic-left-off` |
| X6 | `apps/web/e2e/uat/cross-site.spec.ts` | `uat-x6-vectorbase`, `uat-n8-plasmodb` (the plasmodb half) | - |
| R1 | none: an operator takes a site down | - | - |
| R2 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| R3 | none: needs a provider key | - | - |
| R4 | none: an operator stops the worker | - | - |
| R5 | none: thirty real edits | - | - |
| R6 | `apps/web/e2e/uat/first-run.spec.ts` | - | - |
| R7 | none: needs a slow site | - | - |
| R8 | none: an operator spends the allowance | - | - |
| D1 | none: a check against the deployment | - | - |
| D2 | none: a check against the deployment | - | - |
| D3 | none: a check against the deployment | - | - |
| D4 | none: a check against the deployment | - | - |
| D5 | none: a check against the deployment | - | - |
| D6 | none: a check against the deployment | - | - |
| D7 | none: a check against the deployment | - | - |
| D8 | none: a check against the deployment | - | - |
| D9 | none: a check against the deployment | - | - |
| D10 | none: a check against the deployment | - | - |
| D11 | none: a check against the deployment | - | - |
| L1 | `apps/web/e2e/uat/layout-access.spec.ts` | - | - |
| L2 | `apps/web/e2e/uat/layout-access.spec.ts` | - | - |
| L3 | `apps/web/e2e/uat/layout-access.spec.ts` | - | - |
| L4 | `apps/web/e2e/uat/layout-access.spec.ts` | - | - |
| L5 | `apps/web/e2e/uat/layout-access.spec.ts` | - | - |

## Coverage

Where each rule, card, background tool, thread part, command, settings tab and refusal is exercised. `code only` marks an invariant no screen can show; its test in the repository holds it.

### WDK-MAP rules ([PathFinder mapping rules](../wdk/pathfinder/rules/pathfinder-mapping.md))

| Rule | Flows |
|---|---|
| WDK-MAP-001, eleven parameter kinds | S9 (string), S5 (input step), S1 (single pick), F2 and S9 step 3 (multi-pick tree) |
| WDK-MAP-002, only a value reaches the wire | S9, R2 |
| WDK-MAP-003, the nested tree only at the WDK boundary | V1 step 7, S7, S8 |
| WDK-MAP-004, a tool reaches WDK through a served function | code only |
| WDK-MAP-005, no PathFinder module opens a WDK connection | code only |
| WDK-MAP-006, a WDK step id beside PathFinder's own | S9 step 1, F8 step 2 |
| WDK-MAP-007, WDK-shaped browser types owned by the domain | code only |
| WDK-MAP-008, shared types are PathFinder types with WDK names | code only |
| WDK-MAP-009, the orthology round trip | S6 |
| WDK-MAP-010, a separation offers bindable leaves counted in a strategy | V4 |

### Cards

| Card | Flows |
|---|---|
| Question card (`consult_user`) | N1, N8, X4 |
| Proposal card (`propose_changes`) | N7, N12, C9, V3 |
| Adoption card (`adopt_separating_strategy`) | V4, V5 |
| Approval of a background tool | V3 (`optimize_search_parameters`), V4 (`separate_controls`) |
| Approval of an edit | S13 and C8 (`clear_strategy`), N5 (`delete_step`), S12 (`replace_subtree`) |

### Background tools

| Tool | Flows |
|---|---|
| `run_control_tests_on_step` | V2, V4 step 6 |
| `optimize_search_parameters` | V3 |
| `run_eda_compute` | E2, E4, E6, F11 |
| `separate_controls` | V4, V5 |

### Thread parts (`KnownDataPartKind`, 31)

| Part | Flows | Part | Flows |
|---|---|---|---|
| `data-sub-agent-call` | S1 | `data-memory-retrieved` | M3 |
| `data-sub-agent-step` | S1 step 4 | `data-gene-set` | G1 |
| `data-ledger-update` | V1 step 8 | `data-strategy-revision` | V1 step 9 |
| `data-background-task-started` | V2, E2 | `data-user-question-answers` | N1 step 3 |
| `data-task-progress` | V2, E2, V4 | `data-conversation-title` | F4 |
| `data-task-completed` | V2, E2, F11 | `data-scratchpad-updated` | M4 |
| `data-control-test-results` | V2 | `data-turn-usage` | A3 |
| `data-evidence-card` | V1 | `data-turn-status` | F10 |
| `data-separation-result` | V4 | `data-turn-stopped` | F10 step 3 |
| `data-strategy-link` | E2 | `data-turn-failed` | R4, N6 |
| `data-strategy-meta` | F6 step 5 | `data-lead-usage` | A1 |
| `data-graph-snapshot` | S1 | `data-tool-summary` | S1 step 4 |
| `data-graph-cleared` | S13 | `data-eda.analysis-state` | E2 |
| `data-variant-comparison` | V7 | `data-eda.subset-preview` | E2 |
| `data-scored-comparison` | V3 | `data-eda.viz` | E2, E3 |
| `data-research.sources` | S15, V6 | | |

### Slash commands and settings tabs

| Item | Flows | Item | Flows |
|---|---|---|---|
| `/new` | C2 | `Model` | A1 |
| `/rename` | C3, F6 | `Provider keys` | A2, R3 |
| `/export` | C4, C5, C6, G2 | `Data` | A4, H1 |
| `/import` | C7, G4 | `Memory` | M5 |
| `/help` | C1 | `Privacy` | A5 |
| `/clear` | C8, S13 | `Advanced` | A6 |
| `/analyze` | C9 | `Seeding` | A7 |
| `/summarize` | C10 | | |
| `/diagnose`, `/explain` | C11 | | |

### Refusals

| Refusal | Flows |
|---|---|
| Injection screen (`This message was refused by prompt-injection screening. ...`), and the 503 when it cannot judge | N6 |
| Attachment too large, not readable, over 6 files, over 20 MB | C15, C16 |
| No registered VEuPathDB login (`WDK_LOGIN_REQUIRED`) | F1 |
| Another VEuPathDB account than the session's (`WDK_IDENTITY_MISMATCH`) | F12 step 8 |
| A site down (`SITE_UNAVAILABLE`, `Couldn't reach <site>`) | F3, R1 |
| Cross-organism INTERSECT | N3 |
| Off-topic redirect | N10 |
| An organism another site holds (the portal sentence) | N8, X6 |
| Another site's experiment never bound | N9 |
| A qualifier no search states (`No search states it`) | N2 |
| An empty step (`Not supported: the build pushed ... left 1 empty`) | N4 |
| A delete the tree cannot place | N5 |
| An offer declined, then a bare yes | N7 |
| A second build on a built conversation | N13 |
| A provider refusing the researcher's key; keys off | A2, R3 |
| The monthly allowance spent | R8 |
| The worker stopped | R4 |
| A VEuPathDB 4xx on a step | R2 |

Gaps: none left open in the lists above. Flows marked "not measured" (A2, A7, F6 step 5, N9 step 2, N13, R3, R5, R8, V6, V7, D1 to D11) carry expectations from the code and are measured at UAT start.
