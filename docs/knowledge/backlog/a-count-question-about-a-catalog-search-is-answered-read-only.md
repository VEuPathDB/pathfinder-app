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

**Why it happens.** The comparison tool takes variants of the strategy's own searches only, the Lead writes search names without a catalog lookup, and the refusal is reported as a catalog absence.

**Fix.** A read-only count of a catalog search resolved through `search_for_searches` and the parameter lookup (an anonymous report, no step); a reply may say a search is absent only when a catalog lookup of this turn returned nothing; the counts this conversation measured stay answerable through `[count:]` on the facts.

**What you'd get.** "The InterPro domain search finds N genes; your first product text search found 70; the current strategy holds 1. Nothing was changed."
