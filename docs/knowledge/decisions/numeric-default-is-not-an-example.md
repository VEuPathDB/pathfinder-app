---
type: Decision
title: A number's initial value is a default, not an example
description: WDK types numeric bounds as strings, so the free-text guard swallowed their defaults and asked five needless questions on one search.
tags: [agents, parameters, wdk-alignment, frame]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# What "use defaults" turned out to mean

The backlog carried this as a policy gap: a user saying "pick sensible defaults rather than asking me" had no mechanism behind it, so the obvious move was to build one -- some notion of authorised guessing.

Diagnosing first was worth it. On the drug-target strategy, **7 open slots sat in only two criteria**, and five of them were on `GenesBySnps`:

```
MinPercentMinorAlleles  MinPercentIsolateCalls  occurrences_lower
dn_ds_ratio_lower       snp_density_lower
```

Every one of those has a WDK-declared initial value (`0`, `20`, `0`, `0`, `0`). They were not ambiguous. They were **already answered, and we were throwing the answer away.**

# The cause

`_is_free_text_query` suppresses a default for a visible, required, vocabulary-less `string` param. That guard is right and hard-won: `GenesByText` ships `*reductase` as the *example* in its form, and inheriting it turns an odorant-binding-protein search into a reductase search.

But **WDK reports numeric bounds as `type: "string"` with `isNumber: true`**. So every numeric bound matched the free-text shape, lost its default, and became a Tier-3 question.

# The fix

Carry `is_number` onto `ParameterInfo` and exclude numbers from the guard. A number's `initialDisplayValue` is what PlasmoDB pre-fills in its own form; using it is not a guess, it is the WDK-faithful answer. `MinPercentIsolateCalls = 20` is a curated default, and asking the user instead is *less* faithful, not more cautious.

Measured after the change on live WDK: that criterion went from 5 open slots to **0**, `readyToBuild: True`, with `MinPercentMinorAlleles=0` and `MinPercentIsolateCalls=20` filled from WDK -- while the user's own constraints (`dn_ds_ratio_upper=1.3`, `occurrences_upper=1000`) were bound as stated.

# Why no defaults-authorisation feature was built

Five of seven slots were a bug. The remaining two (`min_expression_percentile`, `samples_percentile_generic` on the DeRisi microarray) are genuine choices that change the result, and the contrast-pair guard must keep asking regardless -- defaulting both halves of a reference/comparison pair gives a degenerate all-vs-all contrast returning zero DE genes.

So the honest answer to "why is it asking so much" was not "add a way to skip questions". It was "stop asking questions WDK already answered".

# Anchor

`_is_free_text_query` in `veupathdb_mcp/catalog/param_dag.py` and `is_number` on `ParameterInfo`. Guarded by `veupathdb-mcp: tests/unit/catalog/test__param_binding.py`, which pins the five live SNP bounds and keeps the `*reductase` suppression.
