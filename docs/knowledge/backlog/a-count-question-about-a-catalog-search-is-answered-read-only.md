---
type: Backlog
title: A count question about a catalog search is answered read-only
description: compare_search_variants counts only searches the strategy runs, so a question comparing a catalog search the strategy does not run gets guessed search names, four refusals and a false claim that the search is absent.
tags: [lead, comparisons, catalog]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A count question about a catalog search is answered read-only

**What I did.** On amoebadb, with a one-step strategy on `GenesByGoTerm` (1 gene) that replaced a `GenesByText` step (70 genes), asked whether a protein domain search would find more genes than the product text search, both counts, nothing changed.

**What I got.** Four `compare_search_variants` calls with `GenesByProteinDomain`, `GenesByProductDescription`, `GenesByInterProDomain` and `GenesByInterPro`, each refused: "is no search a step of this strategy runs, and each variant is counted in place in the strategy's result". No `search_for_searches` ran. Reply: "that search is not available in the current catalog". amoebadb serves `GenesByInterproDomain`. The 70 measured earlier appears in no reply.

**Why that's wrong.** Two count questions get no number, the researcher is told a search does not exist, and a count the conversation measured is withheld.

**Done.** `count_search` and `genes_in_search` (`ai/tools/standalone/search_reads.py`)
count a catalog search and test gene ids against it read-only, with no step; an
unlisted search name is refused with what the catalog lookup finds, and
`compare_search_variants` points a search no step runs to `count_search`.

**What remains.** A reply may still say a search is absent when no catalog lookup
of the turn returned nothing for it. The Lead runs no `search_for_searches` of its
own, FRAME runs it inside the sub-agent where the Lead's turn record does not see
it, and an absence claim names no search ("that search is not available"), so a
check would need loose phrase matching that refuses good replies after a FRAME
lookup. The fix records each catalog lookup a sub-agent ran, with its query and
its hits, on the turn record the reply check reads, and refuses an absence clause
only when the turn holds no lookup at all.

**What you'd get.** A reply that says a search is absent only after a lookup of
the turn found nothing.

**Also remaining.** On tritrypdb, asked which of 8 sampled Trypanosoma congolense
IL3000 kinases have a predicted signal peptide. `genes_in_search` read
`GenesWithSignalPeptide` (1,094 genes) and held none of the 8; the reply read "no
shared genes were returned 0 genes", the shared count standing after a clause that
already says none. The tool names its references but not how a check that holds
no gene is said. The fix states it in `genes_in_search`: name each held gene with
`[record:<id>]`, and when none is held say so, with `[compare:asked genes]` and no
shared count.
