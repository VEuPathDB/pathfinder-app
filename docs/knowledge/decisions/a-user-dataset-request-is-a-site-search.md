---
type: Decision
title: A user-dataset request is a site search
description: A request on the researcher's own upload runs the site's user-dataset search of the upload's type. A search is one when it declares a userDatasetType; its dataset parameter takes an upload the researcher's VDI listing holds and its vocabulary, read under their token, lists. A gene list binds GenesByUserDatasetGeneList in FRAME; a DESeq2 cut or a phenotype subset of an upload is exported on GenesByDESeqUserDataset or GenesByPhenotypeUserDataset. Running every user-dataset request through the EDA compute and the generic export was rejected.
tags: [user-datasets, vdi, eda, frame, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-09-29T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-09-29T00:00:00Z }
status: stable
---

# What was decided

- **Which searches.** A WDK search that declares `properties.userDatasetType` reads the researcher's
  uploads of that VDI type. On every genomics site three do: `GenesByDESeqUserDataset`
  (`rnaseqrc`), `GenesByUserDatasetGeneList` (`genelist`) and `GenesByPhenotypeUserDataset`
  (`phenotype`). The dataset parameter is the search's one single-pick vocabulary parameter
  (`eda_dataset_id`, `geneListUserDataset`). The rule reads those two facts, never a list of
  search names (`services/strategies/user_dataset_searches.py`).
- **Which uploads.** An offer is an upload the researcher's VDI listing holds installed on the site,
  of the search's type, whose id the dataset vocabulary lists under the researcher's token: the VDI
  id for a gene list, `EDAUD_<id>` for an EDA-backed upload. The catalog caches a search definition
  per process, and its vocabulary is whichever account read it first, so the vocabulary is read again
  under the researcher's token.
- **A gene list binds in FRAME.** `GenesByUserDatasetGeneList` is a plain sheet search. A
  `set_criterion` on it binds only a value that is one of the researcher's uploads; a null, the
  site's `bla` placeholder or another account's id is refused with the uploads by name and value,
  and an account with no gene-list upload is told to upload one on the site
  (`_frame_proposals.refuse_unmatched_values`).
- **An EDA-backed upload is exported on its own search.** `GenesByDESeqUserDataset` and
  `GenesByPhenotypeUserDataset` carry `eda_analysis_spec`, so FRAME keeps them as the analysis
  workflow's criteria (see [an EDA analysis is a criterion of the spec](an-eda-analysis-is-a-criterion-of-the-spec.md)).
  The export of an upload's study writes the same two parameters on the user-dataset search of the
  upload's type that reads the export's kind: a volcano cut on the search the site gives a DE
  notebook (`edaNotebookType`), a subset on one it gives none (`services/eda/steps.py::on_the_user_dataset_search`).
  A curated study, and a subset of counts, keep `GenesByEdaVizWithCompute` and `GenesByEdaSubset`.
  The step then opens on the site as "RNA-Seq Differential Expression (User Datasets)", in the
  notebook where the researcher edits the groups and the cut.
- **The cut is not a parameter.** `GenesByDESeqUserDataset` has no threshold parameters: it
  takes the upload (`eda_dataset_id`) and the analysis spec (`eda_analysis_spec`), the same pair
  the generic export takes, and the cut is the volcano inside the spec. A request's stated cut is
  therefore written into the spec, never bound as a step parameter.

# What was rejected

**The EDA compute plus the generic export for every user-dataset request.** A researcher on cedar
asked for DESeq2 on an uploaded A. gambiae RNA-Seq study and then for "log2 fold change > 5 and
p-value < 1e-10". PathFinder ran the compute and exported `GenesByEdaVizWithCompute`, 0 genes, and
never considered the site's three user-dataset searches. Measured on build 71 (2026-09-29) on the
dev account's own uploads:

| | plasmodb | vectorbase |
|---|---|---|
| `GenesByDESeqUserDataset`, 2-fold and 0.05 / log2 5, 1e-10, up only | 39 / 16 | 39 / 16 |
| `GenesByEdaVizWithCompute`, the same two parameters | 39 / 16 | 39 / 16 |
| `GenesByUserDatasetGeneList` on a 20-gene upload | 20 | 20 |
| `GenesByPhenotypeUserDataset` and `GenesByEdaSubset`, `fitness_score` -10 to -2 | 32 and 32 | 35 and 35 |

The two DESeq exports answer the same genes, so the zero was the researcher's cut on that study,
not the export path; no site-side "Get answer" fault reproduced. What the generic export cost was
the rest: a gene list has no EDA form at all, so the compute route could not express it, and the
generic step opens on the site as "Gene Dataset Filtering", a page with no groups and no cut to edit.
`GenesByDESeqUserDataset` also runs the compute itself when its spec names a comparison nobody
computed (a swapped comparison counted 16 down-regulated genes in 13 s, from `no-such-job`).

# Anchor

`services/strategies/user_dataset_searches.py`, pinned by
`tests/unit/services/strategies/test_a_user_dataset_search_reads_the_researchers_upload.py` (recorded
sheets of both sites), `tests/unit/ai/tools/test_a_user_dataset_proposal_names_the_researchers_upload.py`,
`tests/unit/services/eda/test_an_upload_exports_on_its_user_dataset_search.py`,
`tests/unit/ai/tools/test_the_agents_export_of_an_upload_runs_its_user_dataset_search.py`, and the live checks
`tests/integration/strategies/test_wdk_user_dataset_searches.py`. The flows are
[UD1 to UD4](../uat/flows-user-datasets.md).
