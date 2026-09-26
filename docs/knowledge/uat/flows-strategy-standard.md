---
type: TestPlan
title: UAT flows - building strategies, standard
description: One search, INTERSECT, UNION, MINUS, an orthology transform, the round trip that keeps the source organism, saved and site strategies brought into a conversation, the four edits, clear, and the questions a search answers; each with the step layout and the gene counts VEuPathDB returns.
tags: [uat, flows, strategies, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Building strategies, standard (S)

Every count below is genes (WDK `estimatedSize`), measured on build 71 on 2026-09-24 by building the same tree under the dev login (see [sites and accounts](sites-and-accounts.md)). Parameters unless stated: `GenesWithSignalPeptide` `signalp_version=SignalP-6.0`; `GenesByTransmembraneDomains` `min_tm=2`, `max_tm=99`; `GenesByOrthologs` `isSyntenic=no`. "Measured run" is the dev debugger run of the same prompt with `openai:gpt-5.6-luna` (see [findings](findings.md) for the method).

**What every build shows (check it in each S flow):**

| Where | Expect |
|---|---|
| Status line under the reply | `Planning...`, then `Checking...` |
| Trace | Groups `PLANNING` and `CHECKING` (CSS); rows `Find searches`, `Read a search`, `Choose a search`, `Arrange the steps`, `Read the strategy`, `Count results`, `Read sample records` |
| Figure `Strategy updated` | caption `<n> steps, <root count> genes` |
| Figure `Evidence` | verdict `Supported`; step table `Step`, `Recorded at the build`, `On the site at the check`, both columns equal; `<m> of <m> requirements met`; up to 8 sampled genes; link `Open in <Site>` |
| Reply | names each step by the search it runs (`Predicted Signal Peptide`, `Transmembrane Domain Count`, `Transform by Orthology`) with the reason, and states the root count |
| Right rail `Strategy` | opens by itself; footer `<n> steps`; `Open` goes to the canvas |
| Canvas (`Open`) | topbar `<n> steps` and `Saved`; each search node shows `<count> genes`; combine badge `Intersect`, `Union`, `Minus`, `Right minus`, `Colocate` |
| The site (`Open in <Site>`) | the same tree and counts |

Cleanup for every S flow: F7 step 4 (delete with `Also delete strategy from <site name>` ticked).

## Per-site prompts and numbers for the core flows

`<X>` and `<Y>` per site:

| Site | `<X>` | `<Y>` | S1 | S2 | S5 |
|---|---|---|---|---|---|
| plasmodb | Plasmodium falciparum 3D7 | Plasmodium vivax P01 | 479 | 116 (479, 840) | 142 |
| vectorbase | Anopheles gambiae PEST | Aedes aegypti LVP_AGWG | 2,928 | 343 (2,928, 1,871) | 850 |
| toxodb | Toxoplasma gondii ME49 | Neospora caninum Liverpool | 720 | 78 (720, 946) | 145 |
| fungidb | Aspergillus fumigatus Af293 | Aspergillus nidulans FGSC A4 | 748 | 64 (748, 1,341) | 257 |
| veupathdb | Plasmodium falciparum 3D7 | Toxoplasma gondii ME49 | 479 | 116 (479, 840) | 87 |

Measured runs of these prompts: S1 plasmodb 479 (101 s, $0.074). S2 plasmodb 116 in 4 of 5 runs (56 to 124 s, $0.05 to $0.09); the fifth stopped with one search bound (FND-10); vectorbase 343, toxodb 78, portal 116 once and stopped once on a 500 (FND-3); fungidb stopped with one search bound. S5 plasmodb 142 (149 s, $0.086); toxodb 69 and vectorbase 235, both the syntenic count (FND-1).

## S1 - One search - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Sidebar | `New conversation` | Empty thread |
| 2 | Composer | Send `Find <X> genes whose proteins have a predicted signal peptide.` | The build pattern above |
| 3 | Thread | Read | Layout `GenesWithSignalPeptide`; `Strategy updated` `1 step, <S1> genes`; evidence step row `Predicted Signal Peptide` with `signalp_version` `SignalP-6.0` in its parameters (a reply that names the version is welcome and not required) |
| 4 | Trace, row `Choose a search` | Read the summary | It must count genes. Today it reads `479 transcripts` (FND-5, major) |

## S2 - Two searches, INTERSECT - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation, composer | Send `Find <X> genes with a predicted signal peptide and 2 to 99 transmembrane domains.` | Layout `INTERSECT(GenesWithSignalPeptide, GenesByTransmembraneDomains)`; `Strategy updated` `3 steps, <S2> genes`; the two inputs as in the table |
| 2 | Evidence card | Read | 4 requirement rows `Met` (organism, signal peptide, 2 to 99 domains, both must hold), `How` column `parameter`, `search`, `parameter`, `structure` |
| 3 | If the reply says a search was not added and asks to continue | Send `Yes, please finish the transmembrane-domain filter.` | The same layout and count (measured: 116, 130 s, $0.090). The first turn stopping is FND-10 (major) |

Keep this conversation for S5, S6, S9, S10, S11 (branch it with F8 before each, or rebuild).

## S3 - UNION

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | plasmodb, new conversation | Send `Find Plasmodium falciparum 3D7 genes that have a predicted signal peptide or 2 to 99 transmembrane domains.` | Layout `UNION(GenesWithSignalPeptide, GenesByTransmembraneDomains)`; 1,203 genes (479, 840); combine node title `Union`. Measured: 1,203, 140 s, $0.100 |

## S4 - MINUS

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | plasmodb, new conversation | Send `Find Plasmodium falciparum 3D7 genes with a predicted signal peptide, excluding any gene with 2 to 99 transmembrane domains.` | Layout `MINUS(GenesWithSignalPeptide, GenesByTransmembraneDomains)`; 363 genes; combine title `Minus`. Measured: 363, 137 s, $0.098 |

Keep this conversation for S9 and S11.

## S5 - Orthology transform - core

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S2 conversation | Send `Carry these to their orthologs in <Y>.` | Layout `GenesByOrthologs(INTERSECT(GenesWithSignalPeptide, GenesByTransmembraneDomains))` with `organism=<Y>` and `isSyntenic=no`; `4 steps`; root <S5> genes; the transform node is chevron-shaped |
| 2 | Reply | Read | Says the records are `<Y>` genes; sampled genes are `<Y>` ids (plasmodb: `PVP01_...`) |
| 3 | Step editor of the transform (`Edit step`) | Read `Syntenic Orthologs Only?` | `no` |

Today: plasmodb 142 (pass). toxodb and vectorbase build `isSyntenic=yes` (69 and 235 genes): FND-1, blocker. fungidb does not find the transform and asks whether to substitute an ortholog-pattern search: FND-9, blocker. The portal fails on a 500 from an unrelated search: FND-3, blocker.

## S6 - The round trip that keeps the source organism - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A fresh S2 conversation (116 genes) | Send `Keep only those with syntenic orthologs in Plasmodium vivax P01.` | Layout `INTERSECT(INTERSECT(SP, TM), GenesByOrthologs{Pf 3D7, syn}(GenesByOrthologs{Pv P01, syn}(INTERSECT(SP, TM))))`: 9 steps, the seed stated twice; transform counts 67 (to P01) and 68 (back to 3D7); root 67 genes, all `PF3D7_` ids |
| 2 | Reply | Read | Says 67 P. falciparum 3D7 genes and why the way back is needed. Measured: 67, 9 steps, 205 s, $0.114 |
| 3 | Control | The same with `isSyntenic=no` answers 73; a result of 73 means synteny was dropped (the `WDK-MAP-009` measurement) | - |

## S7 - A saved strategy used in another conversation - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S2 conversation, canvas | Click the root node, `More actions`, `Save as reusable...` | Dialog `Save as reusable strategy`, field `Name`; save as `UAT saved S7` |
| 2 | Nav rail `Saved strategies` | Read | h1 `Saved strategies`; row `UAT saved S7`, meta `3 steps`, `116 genes` (joined by a middle dot) |
| 3 | Row | `Use in a new conversation` | Button reads `Inserting...`, toast `Inserted into a new conversation`, the new conversation opens with the Strategy panel showing the 3 steps, 116 genes |
| 4 | A new empty conversation, right rail `Strategy` | `Insert saved strategy`, pick `UAT saved S7`, `Insert` | Toast `Saved strategy inserted`; the steps become the strategy's first steps |
| 5 | Nav rail `Saved strategies` | Read the row | Badge `Used in 2 conversations` (CSS uppercase) |
| 6 | Row | `Delete saved strategy` while other conversations use it | The row reads `Used in 2 conversations`; the delete button is disabled and its title reads `Used in 2 conversations; remove it from them before deleting it.`; the row stays |
| 7 | Cleanup | Delete the two consuming conversations (F7 step 4), then `Delete saved strategy` | A dialog `Delete "UAT saved S7"?` reads `This also deletes the strategy on PlasmoDB, and PathFinder cannot restore it.`; `Delete` gives toast `Saved strategy deleted` and the row leaves the list |

## S8 - A strategy made on the site, opened in PathFinder - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | plasmodb.org, signed in as account A | Build `Predicted Signal Peptide` for P. falciparum 3D7 (SignalP-6.0) and save it | The site shows 479 genes |
| 2 | Sidebar, `Choose an assistant` | `Open a VEuPathDB strategy...` | Dialog `Open a VEuPathDB strategy`, `Pick one of your PlasmoDB strategies, or paste a strategy's link or its numeric id. PathFinder opens a conversation that holds it.`; the list shows the step-1 strategy with `479 results` |
| 3 | Dialog | Pick it, `Open` | Toast `Strategy opened`, `PlasmoDB strategy <id>`; a conversation holding the one step, 479 genes |
| 4 | Dialog | Paste a toxodb strategy link | `That link names a ToxoDB strategy. Switch to ToxoDB to open it.`; `Open` stays disabled |
| 5 | Composer | Send `How many genes does this strategy return?` | 479 |

The app has no "import by signature" of a shared strategy link; this dialog is the import.

## S9 - Edit a parameter - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S4 conversation (363 genes) | Send `Change the transmembrane range to 1 to 99.` | Layout unchanged, `min_tm=1`: MINUS 191 genes (479, 1,628); the signal-peptide step keeps its WDK step id (evidence card link path ends with the same root step id as before) |
| 2 | Reply | Read | Says the signal-peptide criterion was kept. Measured: 191, 128 s, $0.081 |
| 3 | Canvas, the TM node, `Edit step` | Change `Minimum Number of Transmembrane Domains` back to `2`, `Save` | Footer `Saving...` then `All changes saved`; the MINUS reads 363 |
| 4 | Composer | Send `How many genes does this strategy return now?` | 363: the answer reads the hand edit |

## S10 - Add a step - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A fresh S2 conversation (116) | Send `Also keep only those predicted to be exported to the host cell, with an ExportPred score of at least 10.` | Layout `INTERSECT(INTERSECT(SP, TM), GenesByExportPrediction)` with `min_exportpred_score=10`: 5 steps, 25 genes (`GenesByExportPrediction` alone 191) |

Measured today: not added; six binds failed on `GenesByAntibodyArraypfal3D7_microarrayAntibody_Loffler_Natural_Infection` (a 500 on the site) and the reply said "the site could not load the ExportPred search definition" while that definition answered 200 (FND-3, blocker; 141 s, $0.114).

## S11 - Delete a step - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S4 conversation | Send `Remove the transmembrane-domain step.` | Layout `GenesWithSignalPeptide`, 1 step, 479 genes; no approval card (a chat edit). Measured: 479, $0.051 |
| 2 | A fresh S2 conversation, canvas | Hover the TM node, `More actions`, `Delete step` | Dialog `Delete this step?` with the step name and the ways the combine can be resolved (no dialog when there is only one); after `Delete`: 1 step, 479 genes |

## S12 - Replace a subtree - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A fresh S2 conversation | Send `Replace the transmembrane-domain search with the exported-protein prediction, ExportPred score at least 10.` | Layout `INTERSECT(GenesWithSignalPeptide, GenesByExportPrediction)`: 3 steps, 47 genes (479, 191). Measured: 47, 164 s, $0.090 |
| 2 | If an approval card appears | Read | `Replace step 'Transmembrane Domain Count' (GenesByTransmembraneDomains, 840 genes) and the steps under it?`, naming the step the edit replaces; `Deny` / `Approve`; `Approve` gives step 1's result |

## S13 - Clear - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A conversation with a strategy, composer | Type `/clear`, Enter | The message `Clear the current strategy by calling clear_strategy with confirm=true.` is sent; an approval card `Clear the strategy? This removes every step from this conversation and from VEuPathDB.` with `Deny` / `Approve`; trace summary `Waiting for you` |
| 2 | Approval card | `Deny` | `Denied`; a reply says the strategy is unchanged and asks for approval to clear |
| 3 | Composer | `/clear` again, `Approve` | `Approved`; caption `Strategy cleared - user cleared the strategy`; reply "The current strategy has been cleared."; the Strategy panel shows `No strategy built yet`; the strategy is gone on the site. Measured: deny 12 s, approve 10 s, $0.004 each |

## S14 - A count question builds - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `How many protein-coding genes does 3D7 have?` | Layout `GenesByGeneType` (`geneType=protein coding`, pseudogenes excluded): 1 step, 5,318 genes; the reply says 5,318. Measured: 5,318, 102 s, $0.070 |

## S15 - A question about one gene does not build - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `What does PF3D7_0708400 do?` | No `Strategy updated`, no Strategy panel steps; a figure `Sources` with literature links; the reply names heat shock protein 90. Measured: 31 s, $0.015 |

## S16 - Change an operator on the canvas - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A fresh S2 conversation, canvas | Click the edge into the combine, `Change operator` (CSS), `Union` | The badge and the title read `Union`, 1,203 genes; topbar `Saved` |
| 2 | Composer | Send `How many genes does this strategy return now?` | 1,203 |
