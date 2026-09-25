---
type: TestPlan
title: UAT flows - verification and evidence
description: The evidence card every check leaves, control tests on a step, the parameter sweep, and a strategy built from controls (the durable run, its approval, its progress, the offer with its ablation column, a yes that builds and hands the controls to the check, and a no with a comment).
tags: [uat, flows, verification, evidence, controls, durable]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Verification and evidence (V)

All on plasmodb, through a deployment whose worker is up (`D3` in [deployment checks](flows-deployment.md)). The control set is the 80 positives and 40 negatives below, pasted as text. They are the ids the seed "PF3D7 Signal Peptide Genes" carried until it was re-read on 2026-09-24; the seed now holds another list, so use this one:

```
Positive controls: PF3D7_0100600 PF3D7_0100800 PF3D7_0100900 PF3D7_0101000 PF3D7_0101800 PF3D7_0101900 PF3D7_0102300 PF3D7_0102500 PF3D7_0102700 PF3D7_0103900 PF3D7_0104500 PF3D7_0105400 PF3D7_0106600 PF3D7_0107300 PF3D7_0107900 PF3D7_0108700 PF3D7_0109100 PF3D7_0112100 PF3D7_0113000 PF3D7_0113900 PF3D7_0114200 PF3D7_0114500 PF3D7_0114700 PF3D7_0115300 PF3D7_0115400 PF3D7_0115600 PF3D7_0200200 PF3D7_0200400 PF3D7_0200500 PF3D7_0200600 PF3D7_0201000 PF3D7_0201200 PF3D7_0201300 PF3D7_0201400 PF3D7_0203900 PF3D7_0204100 PF3D7_0204600 PF3D7_0207400 PF3D7_0207500 PF3D7_0207600 PF3D7_0207700 PF3D7_0207800 PF3D7_0207900 PF3D7_0208000 PF3D7_0208500 PF3D7_0209000 PF3D7_0209300 PF3D7_0212600 PF3D7_0214900 PF3D7_0215000 PF3D7_0215300 PF3D7_0216600 PF3D7_0220300 PF3D7_0220500 PF3D7_0220800 PF3D7_0221000 PF3D7_0221200 PF3D7_0221400 PF3D7_0222500 PF3D7_0222700 PF3D7_0222800 PF3D7_0223200 PF3D7_0223400 PF3D7_0300400 PF3D7_0300500 PF3D7_0300700 PF3D7_0300800 PF3D7_0300900 PF3D7_0301000 PF3D7_0302200 PF3D7_0302500 PF3D7_0303900 PF3D7_0304600 PF3D7_0305000 PF3D7_0307400 PF3D7_0309100 PF3D7_0310400 PF3D7_0311200 PF3D7_0311600 PF3D7_0311700
Negative controls: PF3D7_0111300 PF3D7_0215800 PF3D7_0218000 PF3D7_0219600 PF3D7_0308000 PF3D7_0317200 PF3D7_0317400 PF3D7_0408500 PF3D7_0409600 PF3D7_0411900 PF3D7_0419600 PF3D7_0508800 PF3D7_0510500 PF3D7_0517400 PF3D7_0625300 PF3D7_0630300 PF3D7_0705300 PF3D7_0705400 PF3D7_0717500 PF3D7_0726300 PF3D7_0914800 PF3D7_1015800 PF3D7_1017000 PF3D7_1029900 PF3D7_1111100 PF3D7_1112600 PF3D7_1127100 PF3D7_1211300 PF3D7_1211700 PF3D7_1215900 PF3D7_1234300 PF3D7_1241700 PF3D7_1317100 PF3D7_1334100 PF3D7_1335500 PF3D7_1355100 PF3D7_1361900 PF3D7_1411400 PF3D7_1417800 PF3D7_1429900
```

What the site returns for these controls (build 71, 2026-09-24: each step built under the dev login, its gene ids read and matched to the 120 ids):

| `GenesWithSignalPeptide` `signalp_version` | Genes | Positives returned | Negatives returned |
|---|---|---|---|
| SignalP-6.0 | 479 | 52 of 80 | 2 of 40 (`PF3D7_0508800`, `PF3D7_1215900`) |
| SignalP-5.0 | 649 | 70 of 80 | 2 of 40 (`PF3D7_0508800`, `PF3D7_1411400`) |
| SignalP-4.1 | 572 | 76 of 80 | 1 of 40 (`PF3D7_1411400`) |

## V1 - The evidence card of a build - core, every site

Check on the S1, S2 and S5 builds of [standard flows](flows-strategy-standard.md).

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Figure `Evidence` under the reply | Read the caption | `<m> of <m> requirements met, 8 of 8 sampled genes fit, <n> steps counted on the site.` when every sampled gene fits; otherwise the sample clause counts each fit word (`5 fit, 3 unclear`) |
| 2 | Verdict | Read | `Supported` |
| 3 | Step table | Read | One row per step: `Step`, `Recorded at the build`, `On the site at the check`; the two counts equal; no `(changed on the site)` |
| 4 | Requirement table | Read | `Requirement`, `Answered by`, `How`, `Status`; one row per stated requirement with `Message 1` beneath; every `Status` `Met` |
| 5 | Sampled genes | Read | `Gene`, `Product`, `Fits`, `Why`; genes of the requested organism; `Why` cites a record value (S1: `signalp_60_probability=...`) |
| 6 | `Sources the check read` | Click one | The site's gene record page opens |
| 7 | `Open in <Site>` | Click | The site shows the same tree and root count |
| 8 | Right rail `Progress`, `Checking` tab | Read | The same card, with `complete yes`, `successful yes` |
| 9 | Composer | Change a parameter (S9), then reopen the older card in the rail | `Superseded: the strategy changed after this check.`; the older answer carries `Superseded - strategy changed since this answer` |

A card that shows `0 of 8 sampled genes fit` beside `Supported` when every gene is `Unclear` is FND-6 (major).

## V2 - Control tests on a step - core on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S1 conversation (479 genes) | Send `Test this strategy against my controls.` followed by the two lines above | One task row `Run control tests` with a percent, then its summary; one figure `Control tests` (`Table <n>`) |
| 2 | `Control tests` table | Read | Caption `Table <n>. Control tests on Predicted Signal Peptide: target 479 records, 52 positive controls recovered (recall 0.65), 2 negative controls returned (false-positive rate 0.05).`; rows `Positive` 80 / 52 and `Negative` 40 / 2 |
| 3 | Evidence card | Read | Verdict `Not supported` (the controls are not all separated); control table `Positive` 80, 52 returned, 28 not returned, `0.65`; `Negative` 40, 2 returned, 38 not returned, `0.05`; `Negatives returned: PF3D7_0508800, PF3D7_1215900` |
| 4 | Right rail `Tasks` | Read | `Run control tests`, status `complete` |
| 5 | Reply | Read | 52 of 80, 2 of 40, the two negatives named |

Measured today: the reply was right (52 of 80, 38 of 40 excluded, the two negatives named), but the check ran 52 control tests (52 task rows, 521 s) and the card kept only the last partial one: `Negative`, 16 controls, 1 returned, no `Positive` row (FND-2, blocker). $0.031.

## V3 - Parameter sweep with its approval - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The V2 conversation | Send `Optimize the SignalP version of the signal peptide search to recover as many of my positive controls as possible while returning as few of my negative controls as possible.` | An approval card `Optimize parameters needs your approval before it runs.`, `Deny` / `Approve` |
| 2 | Approval card | `Approve` | Task row `Optimize parameters` with `~900 s` and a percent; the Tasks panel lists it |
| 3 | Thread, when done | Read | A figure `Scored variants` (`Table <n>`), headers `Variant`, `MCC`, `F1`, `Precision`, `Sensitivity`, `Balanced accuracy`, the `winner` badge on SignalP-4.1 (76 of 80, 1 of 40, 572 genes), then SignalP-5.0, then SignalP-6.0 |

Measured today: the sweep never ran in six turns over two conversations; the approved call carried no controls and failed with `At least one of positive_controls or negative_controls must be provided.` (FND-8, blocker).

## V4 - Controls in, strategy out - plasmodb

The tree depends on the budget and on which candidates the site answers that day, so this flow checks invariants, with today's run as the example.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Find me a strategy that separates these controls, in exact mode.` followed by the two lines above | A reply that proposes the run in words (the two lists, exact mode, a budget of about 600 requests, about five minutes). No run yet |
| 2 | Composer | Send `Yes, run it.` | Approval card `Run the separation? It measures candidate searches against your controls on the site and takes about five minutes.`, `Deny` / `Approve` |
| 3 | Approval card | `Approve` | Task row `Separate the controls`, `~300 s`; progress lines: `Resolved 80 positive and 40 negative ids`, `Uploaded the controls as one dataset`, `Collected <n> candidates: ...`, one line per measured search (`<search>: <p> of 80 positives, <q> of 40 negatives, <genes> genes`), `Assembled the exact strategy from <k> criteria`, `The assembled strategy returns <p> of 80 positives and <q> of 40 negatives in <genes> genes` |
| 4 | Figure `Separation` | Read | A matrix `Positives returned`, `Positives missed`, `Negatives admitted`, `Negatives excluded`; the offered tree; the criteria table `Search`, `Its own step`, `Ablation` with one `without it: <+/-p> positives, <+/-q> negatives` line per criterion; `<i> of <m> measured searches tell the positives from the negatives`; `<used> of <budget> requests`; when it falls short, one sentence per shortfall |
| 5 | Adoption card | Read | `Build the separating strategy: ...?` or `Build the closest strategy found: ...?`, a `Why not? (optional, sent with a no)` box, `No` / `Yes` |
| 6 | Adoption card | `Yes` | `You said yes.`; `Strategy updated` with the offered tree; every step count equals the offer's; the check runs `Run control tests` on the root with the same 120 ids |
| 7 | Evidence card | Read | The positive and negative counts equal the offer's `<p> of 80` and `<q> of 40`; the step table equals the site |

Measured today (budget 600): 39 candidates, 30 measured, 18 informative, 581 of 600 requests, 135 s. Offer `Build the closest strategy found: 3 searches returning 75 of 80 positives and 3 of 40 negatives in 1,221 genes?`; tree `UNION(UNION(GenesWithSignalPeptide, GenesByGoTerm GO:0044217), GenesBySubcellularLocalizationpfal3D7_subcellular_localization_ApicoplastTargeting_RSRC)`; ablation `without it: -17 positives, -1 negatives`, `without it: -9 positives, 0 negatives`, `without it: -9 positives, -1 negatives`. After `Yes`: 5 steps, counts 479, 637, 957, 495, 1,221 on the site; 2 control tests (the same counts); card `Positive` 80, 75 returned, `0.94`, `Negative` 40, 3 returned, `0.07`, note `Positives among the returned controls: 75 of 78 returned, 80 positives in 120 controls, one-sided hypergeometric p = 5.7e-22`; verdict `Not supported` (no exact separator); 136 s, $0.018. An earlier run the same day at budget 400 offered 61 of 80, 2 of 40, 1,132 genes: the tree moves with the budget; the invariant is that the card, the offer and the site agree.

## V5 - A no with a comment - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Repeat V4 steps 1 to 5 in a new conversation | Type `Too broad for a vaccine screen.` in `Why not?`, `No` | `You said no.`; no model reply; no strategy built |
| 2 | Composer | Send `What did you offer me?` | The reply restates the declined offer's counts and that it was declined; nothing is built |

## V6 - Citations on the evidence card - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send `Find P. falciparum 3D7 genes involved in erythrocyte invasion, using what the literature says about the invasion machinery.` | Trace rows `Literature search`; a figure `Sources` with links; the evidence card's citations block lists each criterion's text with its references (DOI or PMID links) |

Not measured today (the literature source was up; no run reached a cited criterion). Expected: measure at UAT start.

## V7 - Compare two variants of a search - plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S1 conversation | Send `Compare the SignalP-6.0 and SignalP-4.1 versions of this search.` | Trace row `Compare variants`; a figure `Variants` (`Table <n>`) with `Variant`, `Genes`, `Unique to it`: SignalP-6.0 479 genes, SignalP-4.1 572 genes, and the overlap note `<a> vs <b>: <shared> shared, Jaccard <j>` |

Not measured. Expected: measure at UAT start (the two counts are WDK's, build 71).
