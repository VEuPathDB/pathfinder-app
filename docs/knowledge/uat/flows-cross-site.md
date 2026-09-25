---
type: TestPlan
title: UAT flows - cross-site and orthology
description: The same request on two sites uses each site's own searches first; another site's experiments are labelled and never bound; orthology on every component site and across genera on the portal, with the organism sheet each site's transform reaches.
tags: [uat, flows, cross-site, orthology]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Cross-site and orthology (X)

The orthology transform `GenesByOrthologs` exists on every site, but its organism sheet holds only that site's clades (plasmodb: Haemoproteidae and Plasmodiidae; toxodb: Eimeriidae and Sarcocystidae; vectorbase: Arthropoda and Mollusca). Only the portal holds two genera in one strategy. Counts: [sites and accounts](sites-and-accounts.md), build 71, 2026-09-24.

## X1 - The same request on plasmodb and vectorbase - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | vectorbase, new conversation | Send `Which genes are upregulated in female mosquitoes after a blood meal?` | Trace `Find searches` reads `<n> searches, experiments on <other sites>`; the step is VectorBase's own `A. gambiae PEST Transcription profiling by array of blood-fed and sugar-fed mosquitoes adult females ...` (`GenesByMicroarrayDirectagamPEST_microarrayExpression_E-MTAB-1621_Bloodfed_vs_Sugarfed_RSRC`, up-regulated, 2-fold, protein coding): 6 genes, all `AGAP` ids |
| 2 | plasmodb, new conversation | Send the same | No PlasmoDB step and no study analysis. The reply says the data are on VectorBase (a labelled line for another site's experiment is fine) |

Measured: step 1 as expected, 6 genes (WDK: 6; 24 with up or down), 127 s, $0.102. Step 2 opened a VectorBase study through EDA and exported a 0-gene PlasmoDB step (FND-11, major).

## X2 - Own-site searches first, other sites labelled - core, every component site

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Each component site, the S2 prompt of that site | Read the trace row `Find searches` | `<n> searches` for the site's own list; when other sites have close experiments, `, experiments on <site>, <site>` after it; the steps built use only this site's searches |
| 2 | Progress panel, `Planning` tab | Read each criterion | Search names of this site only |

Measured: toxodb `10 searches, experiments on plasmodb`; vectorbase `5 searches, experiments on plasmodb`; plasmodb `experiments on toxodb and fungidb`. No other site's search was bound in any run.

## X3 - Orthology on vectorbase and toxodb - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | vectorbase, the S2 conversation (343 genes) | Send `Carry these to their orthologs in Aedes aegypti LVP_AGWG.` | `GenesByOrthologs(INTERSECT(...))`, `organism=Aedes aegypti LVP_AGWG`, `isSyntenic=no`: 850 genes, `AAEL` ids |
| 2 | toxodb, the S2 conversation (78 genes) | Send `Carry these to their orthologs in Neospora caninum Liverpool.` | Same layout, `isSyntenic=no`: 145 genes, `NCLIV_` ids |
| 3 | Each | Step editor of the transform | `Syntenic Orthologs Only?` reads `no` |

Measured: both built `isSyntenic=yes`: vectorbase 235, toxodb 69 (FND-1, blocker). The vectorbase card read `0 of 8 sampled genes fit` beside `Supported` (FND-6).

## X4 - Orthology on fungidb - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | fungidb, the S2 conversation (64 genes) | Send `Carry these to their orthologs in Aspergillus nidulans FGSC A4.` | `GenesByOrthologs`, `isSyntenic=no`: 257 genes (50 when syntenic) |

Measured: the transform was not found; a question card said "The site does not provide a direct step that carries the current genes to Aspergillus nidulans FGSC A4 ortholog records" and offered an ortholog-pattern search instead (FND-9, blocker). 51 s, $0.050.

## X5 - Across genera on the portal - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | veupathdb, the S2 conversation (P. falciparum 3D7, 116 genes) | Send `Carry these to their orthologs in Toxoplasma gondii ME49.` | `GenesByOrthologs`, `organism=Toxoplasma gondii ME49`, `isSyntenic=no`: 87 genes, `TGME49_` ids |
| 2 | Same, a branch of step 1's source | Send `Carry these to their syntenic orthologs in Toxoplasma gondii ME49.` | 0 genes (no synteny across these genera); the reply says 0 and why; verdict `Not supported` naming the empty step |

Measured: the portal seed built once and failed once; both transform attempts failed on 500s from unrelated search definitions (`GenesByGeneType`, `GenesByRNASeqtgonME49_tgme49_spor_ocyst_rnaseq_ebi_rnaSeq_RSRC`, `GenesByAntibodyArraypfal3D7_microarrayAntibody_Loffler_Natural_Infection`), and the reply blamed the orthology search (FND-3, blocker).

## X6 - An organism the site's sheet does not reach

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | vectorbase, the S2 conversation | Send `Carry these to their orthologs in Plasmodium falciparum 3D7.` | No transform. The reply says VectorBase's transform reaches Arthropoda and Mollusca, that the transform to Plasmodium falciparum 3D7 runs on the VEuPathDB portal, and that the researcher asks there |
| 2 | plasmodb, the S2 conversation | Send `Carry these to their orthologs in Toxoplasma gondii ME49.` | The same, naming Haemoproteidae and Plasmodiidae and ToxoDB (N8) |

Measured: vectorbase refused without naming the portal ("the current VectorBase search cannot target *Plasmodium falciparum* 3D7"); plasmodb asked a question whose "yes" leads nowhere (FND-12, major).
