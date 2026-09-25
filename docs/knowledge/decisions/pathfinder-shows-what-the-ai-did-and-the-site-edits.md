---
type: Decision
title: PathFinder shows what the AI did, and the site is where a researcher edits by hand
description: A screen the site already has (a form, a notebook cell, an upload page, a table to sort and filter) is a link to the site, not a copy; what the site cannot show (the spec, each step's rationale, the evidence card, offers, provenance, notes and memory) is PathFinder's UI. Read-only figures and counts stay in the conversation. The EDA tab is the first surface cut to the line; it reads the shared analysis document fresh on every load. Copying the site's notebook was rejected.
tags: [product, eda, frontend, site-alignment, notebook, read-only]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

**The line.** PathFinder shows what the AI did and why. VEuPathDB is where a researcher edits
by hand. A screen the site already has is a link to the site: a search form, an EDA notebook
cell, the My Data Sets upload page, a result table the researcher sorts and filters. What the
site cannot show is PathFinder's own UI: the spec and its criteria, the rationale of each
step, the evidence card, the offers, the provenance of a count, notes and memory.

**What stays in the conversation.** Read-only figures and counts: the volcano, the subset
histogram, the entity counts, the evidence card's numbers. The conversation is never blind to
what the agent did. A control that only changes the local view of a figure (a hover, a zoom,
the expand toggle of a plot) stays, because it writes nothing.

**What leaves.** Every hand-editing screen the site has:

- the EDA notebook cells: the subset editor (entity tree, variable rows, filter editor, the
  per-variable distribution), the compute configuration form and its progress poll, and the
  volcano threshold controls, which changed the cut an export wrote;
- the upload form, already a link ([a private dataset is uploaded on the site](a-private-dataset-is-uploaded-on-the-site-and-analysed-here.md));
- enrichment and the other result-page analyses, and the workbench, already removed in
  v0.2.0a15 ([VERIFY shows its evidence](verify-shows-its-evidence.md)).

## The EDA tab under the line

The tab (`apps/web/src/features/eda/EdaWorkbench.tsx`) holds:

- the study picker and "Your datasets", which bind a study to the conversation;
- the subset as text: one chip per filter sentence the api derives
  (`services/eda/description.py::filter_summaries`), a count of the filters no sentence
  names, and each entity's subset size against its whole size;
- the comparison as one sentence: method, group A and group B by their labels, the comparator
  variable, the value variable and the identifier variable, each by the name the study gives it
  (`EdaAnalysisState.compute`, built by `description.py::compute_summary`);
- the figure of that comparison, drawn at the cut the analysis stores, with the cut stated in
  words, and the retained and selected counts;
- "Export as step", which names its `source`: `volcano` exports the cut the analysis stores,
  read on the server when the export runs (`services/eda/steps.py::export_analysis_step`),
  and `subset` exports the subset when no figure is drawn;
- one link, "Open in <site>", to the site's own page for the analysis,
  `<site>/app/workspace/analyses/<datasetId>/<analysisId>` (`services/eda/urls.py`), in a new
  tab. That page is where the subset, the comparison and the cut are edited.

The agent configures and runs the comparison from the request through the durable
`run_eda_compute`, and `create_eda_step` exports it as a criterion
([an EDA analysis is a criterion of the spec](an-eda-analysis-is-a-criterion-of-the-spec.md)).
The conversation PATCH takes three actions: `bind`, `export-step`, `unbind`. The routes that
served only the editing cells are gone: `set-filters`, `run-compute`,
`GET /eda/studies/{datasetId}`, `POST /eda/count`, `POST /eda/distribution`, and the raw
`descriptor` on `GET /conversations/{id}/eda`.

## The round trip

An EDA analysis is a shared document. The site and PathFinder address the same analysis id
through the same EDA service (`/users/{uid}/analyses/{project}/{analysisId}`), so an edit made
in the site's notebook is the document PathFinder reads next. Every read takes the document
anew: `GET /conversations/{id}/eda` calls `services/eda/binding.py::read_analysis` on each
request and holds no copy, the tab's query of it is stale at once, and the figure's query
(`POST /eda/viz`) is stale at once and reads the cut from the analysis's own volcano
(`services/eda/compute.py::stored_volcano_cut`, the default cut of 1 and 0.05 when the
comparison stores no volcano) on the site and dataset the conversation bound. The cut keeps a
gene at |effect size| >= its threshold and raw p <= its threshold, the rule WDK's step applies,
on every surface. Opening the tab, or returning to it, therefore shows what the
site holds now.

# What was rejected

**Copying the notebook.** The first tester asked whether PathFinder could carry the site's
notebook cells. The copy was built: a subset cell with an entity tree, variable rows and a
filter editor, a compute form, a progress poll and volcano controls. It is two UIs of one
document that must be kept in step with `web-monorepo/packages/libs/eda/src/lib/notebook/`
by hand, cell by cell, and every rule the site's cells enforce (the shared inputs of the
differential expression preset, the allowed value variables, the date bounds the service
parses) was a rule to restate. It adds no AI value: a hand edit in the copy is the same edit
the site makes, and the agent reads the document the same way whoever wrote it.

**Keeping the threshold controls as a view.** They wrote nothing to the analysis, but they
set the cut "Export as step" exported, so they authored a step. The cut is the analysis's
own volcano setting, edited on the site or asked for in the conversation.

**Caching the analysis in `conversation_analyses`.** A cached copy would show the tab a
document the site had already changed. The row holds the binding and its revision only.

# What would prove this wrong

`tests/integration/http/test_conversation_eda_route.py::test_a_read_after_the_site_edits_the_analysis_carries_the_edit`
changes the upstream document between two reads and requires the second to carry the edit,
with no write from PathFinder. `apps/web/src/features/eda/EdaWorkbench.test.tsx` requires the
tab to render no input, select or textarea, only "Change study" and "Export as step" as
buttons, the site link with the recorded analysis's href, and a fresh read of the analysis and
of its figure on every mount. `apps/web/e2e/feature/thread-surgery/eda-branching.spec.ts`
writes a subset through the site's own EDA service and requires the tab to show it.
