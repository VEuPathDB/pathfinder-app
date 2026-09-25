---
type: Proposal
title: PathFinder EDA integration concept
description: The two seams by which PathFinder can adopt EDA, what an EDA tab of its own would be, and how models are fed EDA knowledge. Concept and surface map only; no execution plan.
tags: [eda, pathfinder, integration, proposal, agents]
generated: { by: claude-code/fable-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-27T00:00:00Z }
status: accepted
---

# PathFinder EDA integration concept

Status: implemented. The facts it
stands on are in `veupathdb-py: docs/knowledge/eda/what-eda-is.md`,
`veupathdb-py: docs/knowledge/eda/eda-wdk-bridge.md`, and `veupathdb-py: docs/knowledge/eda/rest-surface.md`.

## The one-sentence position

EDA is already reachable from PathFinder's existing machinery, because
upstream chose to expose it as ordinary WDK searches with a JSON parameter;
the integration work is therefore agent capability and UI, not transport.

## Seam 1: EDA-backed steps in existing strategies (small)

`GenesByEdaSubset`, `GenesByEdaVizWithCompute`, and the per-dataset
`GenesBy*EdaSubset_*` searches are ordinary transcript searches. PathFinder's
step creation, combining, and strategy persistence need zero changes; the
live proof in `veupathdb-py: docs/knowledge/eda/eda-wdk-bridge.md` ran through the same
answer API our services call. What is missing is authoring:

- **An EDA integration client** (`integrations/eda/`), typed with Pydantic
  models mirroring the io-ts truth (`Analysis`, `Filter` union with its 7
  discriminated types, `Computation`, study/entity/variable trees). Consumes:
  `/studies`, `/studies/{id}`, `/permissions`, `/count`, `/distribution`,
  `/root-vocab`, `/apps`, `/computes/{name}`, `/apps/{app}/visualizations/{viz}`.
- **Catalog treatment.** Today these searches surface as two opaque string
  params, so agents cannot fill them meaningfully. The catalog should mark
  searches carrying `eda_analysis_spec` as EDA-backed, join them to their
  study via `eda_dataset_id` default + `/permissions`, and route param
  authoring to an EDA-specific resolver instead of the generic one.
- **Spec authoring with validation gates.** Build the `NewAnalysis` JSON from
  live study metadata, never from model memory: filters must name real
  entity/variable ids and in-vocabulary values (verify with `/count` before
  creating the step, the same trust posture as our WDK param validation);
  `studyId` in the spec must equal `eda_dataset_id`; a study must carry
  exactly one `VEUPATHDB_GENE_ID` variable or the search fails.
- **Compute-backed steps and pending answers.** WDK signals an unfinished
  compute with a delayed result rather than an answer. The clean PathFinder
  path is to drive the compute itself first (`POST /computes/{name}
  ?autostart=true`, poll `{status}` inside a `@durable_tool` job, which is
  exactly our background-task architecture), and only create the step once
  status is `complete`, so the step never surfaces WDK's delayed-result
  state. The delayed state is now measured
  (`veupathdb-py: docs/knowledge/eda/notebook-presets.md`): the answer API returns
  HTTP 202 `{"message":"WDK-DELAYED-RESULT","status":"accepted"}` while the
  job runs, the WDK request itself auto-starts the compute, and the identical
  request after completion returns the 200 answer - so a client that only
  branches on `response.ok` reads the 202 as success and finds no records.
  The drive-the-compute-first path avoids all of that and is evidence-backed.

## Seam 2: an EDA tab of its own (large)

The genomics sites embed EDA as a notebook inside a question form; ClinEpiDB
ships a full workspace. PathFinder's version of "build the EDA, then use it in
strategies" is a new frontend feature (a tab of its own) that renders
a read-only view of the analysis the agent built, over our own EDA client:

- **Study picker** over `/studies` (759 on PlasmoDB), searchable, in
  `apps/web/src/features/eda/StudyPicker.tsx`; the displayName + description
  text is embedded in the same vector index pattern as our catalog
  (`integrations/embeddings/study_index.py`).
- **Subset and comparison, as text**: the filter sentences and entity counts
  of `descriptor.subset.descriptor`, and the analysis's comparison as one
  sentence, read-only. The agent writes them (`set_eda_filters`, the durable
  `run_eda_compute`); a researcher edits them in the site's own notebook, which
  the tab links. The editing cells that copied the notebook were removed
  ([PathFinder shows what the AI did](../decisions/pathfinder-shows-what-the-ai-did-and-the-site-edits.md)).
- **Visualization cell**: renders the server-computed data with our own
  ECharts components, in `apps/web/src/features/eda/cells/VizCell.tsx`; EDA
  sends data, not images, so we are not importing web-monorepo React. The
  `data-eda.viz` part carries a point cloud, so volcano and scatter render
  and histogram, bar and boxplot get a named notice instead.
- **Export as step**: serializes the notebook state to `eda_analysis_spec` and
  inserts a `GenesByEdaSubset` / `GenesByEdaVizWithCompute` step into the
  current strategy, in `apps/web/src/features/eda/ExportStepButton.tsx` and
  `apps/api/src/pathfinder/services/eda/steps.py`; the cut the analysis's
  volcano stores becomes the step's parameters, exactly as upstream does it. On a
  thread with no strategy the export begins one.
- **Persistence**: saves through `/users/{uid}/analyses/{project}` so analyses
  are visible on the VEuPathDB site too. Upstream stays the SSOT for user
  artifacts, as with strategies; PathFinder stores only the
  `conversation_analyses` binding and its revision counter.

Upstream's notebook presets (`differentialExpression`, `wgcnaCorrelation`,
`antibodyArray` in `web-monorepo/packages/libs/eda/src/lib/notebook/`) encode
which cells and which compute configurations make sense for which data; they
are the template for our typed authoring sheets, the same pattern as
`set_criterion` params_template.

## How models get EDA knowledge

Two layers, and they must not be conflated:

- **Static semantics** (this directory): what a study/entity/variable is, the
  filter algebra, the bridge invariants, the job lifecycle. Small, stable,
  and OKF works for it exactly as it does for WDK rules. Prompt-facing
  material derives from these files; assertions name the upstream that can
  falsify them.
- **Per-study metadata is data, not documentation.** 759 studies times entity
  trees times vocabularies cannot live in prompts or docs and would drift
  within a release. Agents must fetch it at run time through tools (study
  search, entity/variable browse, vocabulary/distribution lookup), the same
  discovery posture as the WDK catalog. Any cached copy needs
  `(baseUrl, studyId, sha1hash)` as its invalidation key, falling back to
  `lastModified` for user-submitted studies, whose `sha1hash` is the empty
  string (12 of 759 on PlasmoDB, 102 of 984 on ClinEpiDB, live 2026-08-27).

## Rejected shapes

- **Re-implementing computes or visualizations client-side**: the service
  computes both the statistics and the plot data; duplicating them guarantees
  disagreement with the sites.
- **Embedding web-monorepo's React EDA components**: different React/runtime
  assumptions and a CRA-era build; we consume the wire protocol instead, as
  we already do for WDK.
- **Static study documentation for models**: see above; it is data.
- **A separate EDA auth path**: the WDK bearer token is the EDA credential;
  guest calls are 401, so the existing
  [registered-login rule](../decisions/wdk-requires-registered-login.md)
  covers EDA unchanged.
