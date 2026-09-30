---
type: TestPlan
title: UAT flows - the researcher's own uploaded datasets
description: A DESeq2 cut on an uploaded counts table, the same cut through the analysis view, an uploaded gene list as a step, and a phenotype upload filtered; each on the site's user-dataset search, with the counts VEuPathDB returns on plasmodb and vectorbase.
tags: [uat, flows, user-datasets, vdi, eda, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-09-29T00:00:00Z }
status: draft
---

# The researcher's own uploaded datasets (UD)

Every count below is genes, measured on build 71 on 2026-09-29 under the dev login, on the three uploads the account holds on each site (`pathfinder-uat-genelist`, `pathfinder-uat-deseq`, `pathfinder-uat-phenotype`; ids in [sites and accounts](sites-and-accounts.md#user-datasets-of-the-dev-account)). The counts table holds 200 genes of the site's reference organism, three `control` and three `treated` samples, 40 genes raised in `treated` (log2 fold change 1 to 8) and none lowered. The phenotype table holds one column, `fitness_score`, over the same 200 genes.

Each site offers three user-dataset searches. Each one declares the VDI type it reads (`properties.userDatasetType`), and its dataset parameter lists the uploads of that type the signed-in account holds:

| Search | Display name | Type | Parameters |
|---|---|---|---|
| `GenesByDESeqUserDataset` | RNA-Seq Differential Expression (User Datasets) | `rnaseqrc` | `eda_dataset_id` (single-pick-vocabulary, `EDAUD_<vdi id>`), `eda_analysis_spec` (string) |
| `GenesByUserDatasetGeneList` | Gene List (User Datasets) | `genelist` | `geneListUserDataset` (single-pick-vocabulary, `<vdi id>`; default `bla`, the site's "Choose ... or Upload one first" entry) |
| `GenesByPhenotypeUserDataset` | Phenotype (User Datasets) | `phenotype` | `eda_dataset_id` (single-pick-vocabulary), `eda_analysis_spec` (string) |

The cut of `GenesByDESeqUserDataset` is not a parameter of its own: it is the volcano inside `eda_analysis_spec`, the same document the generic export `GenesByEdaVizWithCompute` reads. The search runs the DESeq2 compute itself when the spec names a comparison nobody computed yet.

| Measured | plasmodb | vectorbase |
|---|---|---|
| `GenesByDESeqUserDataset`, treated against control, `|log2 FC| >= 1`, `p <= 0.05`, both directions | 39 | 39 |
| the same, `log2 FC >= 5`, `p <= 1e-10`, up only | 16 | 16 |
| `GenesByEdaVizWithCompute` with the same two parameters, each cut | 39, 16 | 39, 16 |
| `GenesByUserDatasetGeneList` | 20 | 20 |
| that list INTERSECT `GenesWithSignalPeptide` (`SignalP-6.0`) | 5 | 3 |
| `GenesByPhenotypeUserDataset`, `fitness_score` from -10 to -2 | 32 | 35 |
| `GenesByEdaSubset` with the same two parameters | 32 | 35 |

The generic export and the user-dataset search answer the same genes, so a zero from one and a count from the other is a site fault; none was measured (`tests/integration/strategies/test_wdk_user_dataset_searches.py`).

Cleanup: F7 step 4 for the conversation. Keep the three uploads: the flows and the live tests read them.

## UD1 - DESeq2 on the uploaded counts, then a stated cut

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation, composer | Send `On my uploaded RNA-Seq dataset 'pathfinder-uat-deseq', find the genes differentially expressed between the treated and the control samples with DESeq2, at the default cutoffs.` | The comparison runs (`Run differential expression`); one step `GenesByDESeqUserDataset`, 39 genes; the facts show `Reference group` `control`, `Compared group` `treated`, the two thresholds as `site default` or `chosen` with the note that no other value was measured |
| 2 | Composer | Send `Set the thresholds for a few tens of up-regulated genes (none down-regulated): log2 fold change > 5 and p-value < 1e-10.` | The same step, 16 genes; the facts show `log2(Fold Change)` `5` and `Significance threshold` `1e-10`, both `stated`, `Effect direction` `upOnly`; the count before this turn's edit (39) beside the new one |
| 3 | Facts | Read | The step's name says which group is higher (`higher in treated`). A tighter cut that counts more genes than the looser one moved the wrong way: the reply must say so beside both counts, and a reply that does not is a major |
| 4 | `Open in <Site>` | Read the step | `RNA-Seq Differential Expression (User Datasets)`; its notebook opens on the same groups and cut |

## UD2 - The same comparison through the analysis view

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation, composer | Send `Open my uploaded dataset 'pathfinder-uat-deseq' in the analysis view, compare treated against control with DESeq2 and show me the volcano.` | The study card and the volcano (39 retained at 2-fold and 0.05); no step until asked |
| 2 | Study tab | `Export as step` | One step on `GenesByDESeqUserDataset`, 39 genes, the same as UD1 step 1 |

## UD3 - An uploaded gene list as a step, intersected with a site search

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation, composer | Send `Take the gene list I uploaded, 'pathfinder-uat-genelist', and keep the genes whose proteins have a predicted signal peptide.` | Layout `(GenesByUserDatasetGeneList INTERSECT GenesWithSignalPeptide)`, 3 steps; `geneListUserDataset` is the upload's id; counts 20 and 479 (plasmodb) or 2,928 (vectorbase), root 5 (plasmodb) or 3 (vectorbase) |
| 2 | Facts | Read | The gene-list step is named `Gene List (User Datasets)`; its dataset value carries the label `pathfinder-uat-genelist` |
| 3 | Account B, which holds no gene-list upload, new conversation | Send step 1 | No step on `GenesByUserDatasetGeneList`; the reply says the account holds no gene-list upload on the site and points at My Data Sets |

## UD4 - A phenotype upload filtered

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation, composer | Send `From my uploaded phenotype dataset 'pathfinder-uat-phenotype', give me the genes with a fitness_score of -2 or lower.` | The subset is set on `fitness_score` and exported: one step `GenesByPhenotypeUserDataset`, 32 genes (plasmodb) or 35 (vectorbase) |
