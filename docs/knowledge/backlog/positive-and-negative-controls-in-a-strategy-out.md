---
type: Backlog
---

# Positive and negative controls in, a strategy out

Release a16. `optimize_search_parameters` tunes the parameters of a strategy the
researcher already built. The researcher called it the naive direction: what
they want is to give the genes they know belong (positives) and the genes they
know do not (negatives) and receive a strategy, either one that returns exactly
those genes or one that returns them and their like, grounded in literature.

## What

A durable task that takes two gene sets and a site, searches the catalog for
criteria that separate them (searches whose result contains the positives and
excludes the negatives, scored by recall on positives at zero negatives, then by
result size), assembles the AND/OR that best separates, and returns a strategy
the Lead can build with the confusion matrix as its evidence. Two modes: exact
(the smallest strategy that returns the positives and none of the negatives) and
similar (the criteria that hold for the positives, so the result is the positives
plus what shares their features). The research tool proposes candidate criteria
from the literature on the positives; the harness measures each proposal the
same way, so a proposal is a hypothesis and the counts decide.

## Constraints

Every score is a real WDK count from a real step, never a model estimate. A
candidate search that cannot take a gene-level constraint is skipped, not
guessed. Runs as a durable task with progress rows (the recipe under Durable
Background Tasks). Regression tests: a known positive and negative set on plasmodb
yields a strategy whose counts the test reads from the site; exact mode returns
no negative; similar mode returns every positive.
