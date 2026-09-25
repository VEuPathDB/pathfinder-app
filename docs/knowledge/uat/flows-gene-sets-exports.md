---
type: TestPlan
title: UAT flows - gene sets and exports
description: Saving a gene set from a strategy, exporting it and the conversation, publishing it to the researcher's VEuPathDB workspace, deleting it, and the links that open the same things on the site.
tags: [uat, flows, gene-sets, exports, vdi]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Gene sets and exports (G)

There is no gene-set page: a gene set appears as a figure in the thread, and `/export` and `/import` reach it from the composer.

## G1 - Save a gene set from a strategy - core, every site

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S2 conversation of the site | Send `Save the genes of this strategy as a gene set named UAT G1.` | Trace row `Save gene set`; a figure titled `UAT G1`, caption `<S2 count> genes on <site id>`, `Gene set created`, pills `Publish to VEuPathDB workspace` and `Delete` |
| 2 | Reply | Read | The set name and the count; the count equals the strategy's root (plasmodb 116) |

Measured on plasmodb: `UAT G1`, 116, source `strategy`; 17 s, $0.012. The reply called them "116 transcripts" (FND-5).

## G2 - Export the gene set and the strategy - core, once

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Composer | `/export`, `Latest gene set on this site (CSV)` | Toast `Downloading <file>`; the CSV holds 116 rows of `PF3D7_` ids |
| 2 | Composer | `/export`, `Latest gene set on this site (TXT)` | The same ids, one per line |
| 3 | Evidence card | `Run GO, pathway or word enrichment in <Site>` | The site's strategy page opens (enrichment runs on the site) |
| 4 | Right rail `Strategy` | The site link (`PlasmoDB`) | The site shows the strategy: 3 steps, 116 genes |
| 5 | Canvas | The topbar's `Open in PlasmoDB`, and the step editor's `Open in PlasmoDB` | The same strategy |

Every link to the site reads `Open in <Site>`, except the Strategy panel's, which reads the site name alone (`PlasmoDB`).

## G3 - Publish to the VEuPathDB workspace - once on plasmodb

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The `UAT G1` figure | `Publish to VEuPathDB workspace` | A `Visibility` select (`private` preselected, `protected`, `public`), `Confirm publish`, `Cancel` |
| 2 | Same | `Confirm publish` | `Publishing...`, toast `Published 116 genes`; a status line `Reading publication status...`, then `Upload <state>, import <state>`, then `Installed on PlasmoDB` |
| 3 | Status line | `Open dataset` | The site's dataset page; its summary reads `116 genes published from the PathFinder gene set 'UAT G1'.` |
| 4 | Cleanup | Delete the dataset on the site; then the figure's `Delete`, `Delete` in `Delete UAT G1?` | `Gene set deleted`; the dialog said `PathFinder removes this gene set and cannot restore it. A dataset published from it stays in your VEuPathDB workspace.` |

A five-gene list installed on PlasmoDB 7.6 s after its upload was accepted (2026-09-04, the VDI decision); measure the 116-gene install time at UAT.

## G4 - Import a gene set from pasted ids - once

See C7 in [composer flows](flows-composer.md): `Imported "UAT import C7" with 3 gene IDs.`, then `/export` of it gives the three ids.
