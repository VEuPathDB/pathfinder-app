---
type: TestPlan
title: UAT flows - studies (EDA)
description: Picking a study, the comparison the assistant runs, the read-only study tab, export as a step, the site's own analysis page and an edit made there, the researcher's own uploaded datasets, and genes the site does not annotate.
tags: [uat, flows, eda, studies, vdi]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Studies (E)

On plasmodb, study "Heat shock response in sensitive mutants (LRR5, DHC)" (`DS_e973eadd57`): 12 samples, genotypes `wildtype`, `delta-DHC mutant` and others. The tab is read-only by decision (see [known limits](known-limits.md)): the subset, the comparison and the cut are edited on the site.

Expected numbers, measured on 2026-09-24: the comparison `wildtype` (group A) against `delta-DHC mutant` (group B), DESeq on sense counts, keeps 201 of 5,490 genes at |effect size| >= 1 and p <= 0.05 (31 higher in the mutant, 170 higher in wild type); the step exported from it answers 201 genes. The same 201 came from the site's own `GenesByDESeqUserDataset` in the private-dataset live checks (L7).

## E1 - Pick a study in the tab - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A new conversation with one message sent, right rail `Studies` | Read | `No study is open`, `Ask the assistant to explore a study, and the subset and its plots appear here.` |
| 2 | Browser | Go to `/<site>/conversation/<id>/eda` | Header `No study selected`; `Back to conversation`; `Your datasets` with `Upload on VEuPathDB`; `Search studies...` |
| 3 | `Search studies...` | Type `h` | `Type at least 2 characters to search studies.` |
| 4 | `Search studies...` | Type `heat shock` | A row `Heat shock response in sensitive mutants (LRR5, DHC)` with `DS_e973eadd57` and its sites |
| 5 | Row | Click | Header title the study name; `Open in PlasmoDB`, `Change study`, `Export as step` (disabled: no filter, no figure); cell `Subset` (CSS) `No filters: the subset is the whole study.`, `12 of 12 Sample`, `68,640 of 68,640 pfal3D7 htseq counts`; cell `Comparison` `No comparison has run on this analysis. Ask for one in the conversation.` |
| 6 | Tab | Look for any input | None: no text field, no select, no editable control |
| 7 | Header | `Change study` | Back to the picker; the Studies panel reads `No study is open` |

## E2 - The assistant runs a comparison - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Open the PlasmoDB study 'Heat shock response in sensitive mutants (LRR5, DHC)' and compare the wild type samples with the DHC mutant samples by differential expression on the sense counts.` | Trace rows `Find studies`, `Read study`, `Open study`, `Filter samples`, `Preview samples`, `Run differential expression`, `Add study step` |
| 2 | Thread | Read the study card | Titled with the study; `8 of 12 Sample, 45,760 of 68,640 pfal3D7 htseq counts`; chip `genotype is one of wildtype, delta-DHC mutant`; `Open in PlasmoDB`; `Open study` |
| 3 | Thread | Read the task row | `Run differential expression`, `~120 s`, progress `Checking for a cached result`, `Starting the compute`, `Reading the statistics`, `Compute complete` |
| 4 | Thread | Read the figure | Volcano titled with the effect size (`log2(Fold Change)`); caption ends `201 of 5,490 genes retained).`; `Group A: wildtype - Group B: delta-DHC mutant`; `Gene ids (201)` with `Copy gene ids` |
| 5 | Thread | Read the rest | `Strategy updated` `1 step, 201 genes`, step `Genes that differ between wildtype and delta-DHC mutant` (`GenesByEdaVizWithCompute`); evidence card `Supported` |
| 6 | Reply | Read | DESeq, sense counts, 5,490 genes tested, 201 pass, 31 higher in delta-DHC mutant, 170 higher in wild type |
| 7 | Right rail `Studies` | Read | The study, the analysis name, `1 filter - 1 computation` |

Measured: exactly the numbers above, 146 s, $0.070 (through the worker). The evidence card's sample line reads `0 of 8 sampled genes fit` beside `Supported`: FND-6 (major).

## E3 - The read-only tab after a comparison - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The E2 thread, study card | `Open study` | The tab opens on the same analysis |
| 2 | Tab | Read | Chip `genotype is one of wildtype, delta-DHC mutant`; `8 of 12 Sample`; comparison sentence `DESeq compares wildtype (group A) with delta-DHC mutant (group B) on genotype, reading Sense Count per Gene.`; cut `Higher in either group, \|effect size\| >= 1, p <= 0.05`; selection `201 genes selected, 201 of 5490 retained by the comparison` (no thousands separator here, unlike the thread: a minor); the read-out table `Gene`, `Effect`, `p` and `The first 50 of 201 selected genes are listed.` |
| 3 | Tab | Look for any input | None |
| 4 | Volcano | Hover a point | A tooltip with the gene id, `effect`, `-log10(p)` |

## E4 - Export as a step from the tab - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Open the PlasmoDB study 'Heat shock response in sensitive mutants (LRR5, DHC)' and compare the wild type samples with the DHC mutant samples by differential expression on the sense counts. Do not make a strategy step.` | The comparison runs (E2 steps 2 to 4); no `Strategy updated` |
| 2 | Tab | `Export as step` | `This step is now the strategy's first step.` with `Open the strategy canvas`; `Exported: <step name>` |
| 3 | Right rail `Strategy` | Read | One step, 201 genes |

## E5 - The site's analysis page, and an edit made there - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The E2 tab | `Open in PlasmoDB` | A new tab at `https://plasmodb.org/plasmo/app/workspace/analyses/DS_e973eadd57/<analysis id>` showing the same subset and comparison |
| 2 | The site | Remove the genotype filter and save | - |
| 3 | PathFinder tab | Reload | `No filters: the subset is the whole study.`, `12 of 12 Sample`: the tab reads the site's document |
| 4 | Composer | Send `What is the subset of the open study now?` | The assistant may still describe the old subset: the backlog item "A site edit reaches the Lead's briefing", a known limit |

## E6 - Your own uploaded dataset - plasmodb

Needs a counts file the site accepts: an RNA-Seq count matrix with a sample-details file and no sample column named `label` (the site's importer fails on it). The live check used a stranded matrix of 5,720 genes by 12 samples (545 KB).

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Tab, `Your datasets` | `Upload on VEuPathDB` | The site's own My Data Sets page opens in a new tab (`https://plasmodb.org/plasmo/app/workspace/datasets`) |
| 2 | The site | Upload the matrix | The site accepts it (measured: 202 in 1.5 s, installed in 67.5 to 68.8 s over four runs) |
| 3 | PathFinder tab | Reopen the tab while it installs, then after | The row reads `Installing on VEuPathDB`, then `Your upload` (clickable) |
| 4 | Row | Click | The study opens like a curated one; its source type reads `user_submitted` |
| 5 | Composer | Ask for the same wild type against delta-DHC mutant comparison | The same 201 genes as E2 (measured in the live check: identical gene sets from the upload and from `DS_e973eadd57`) |
| 6 | Account B | Open the tab's `Your datasets` | A's upload is not listed |
| 7 | Cleanup | Delete the dataset on the site | Gone from `Your datasets` at the next open |

## E7 - Genes the site does not annotate - plasmodb

Needs the E6 matrix with three retained gene ids renamed to ids the site does not have (the live check used `PF3D7_9901100`, `PF3D7_9902100`, `PF3D7_9903100`).

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The tab of that upload, after the E6 comparison | `Export as step` | The volcano retains 201; the step answers 198; the tab says `3 of 201 genes are not genes of PlasmoDB (Plasmodium)'s current annotation.` |

## E8 - A study another site publishes - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | plasmodb, new conversation | Send `Which genes are upregulated in female mosquitoes after a blood meal?` | The assistant says mosquito data is on VectorBase and builds nothing on PlasmoDB |

Measured today: it opened a VectorBase study (`Antennal expression following a blood meal`, sites `portal`), ran DESeq (136 of 12,852 genes) and exported a 0-gene step on PlasmoDB, then suggested relaxing thresholds (FND-11, major). On vectorbase the same question bound the site's own blood-fed versus sugar-fed search: 6 genes, which WDK confirms.
