---
type: Backlog
title: Typed requirements are measured
description: Every requirement now carries a typed value and every decision about it reads typed fields, but no gold set fixes how accurate the typed fields must be, and no replay of the saved runs reports the typed accuracy, the untyped share and the share of quotes no message holds. Build the gold set, set its pass threshold, and run the replay.
tags: [requirements, evals, measurement]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: proposed
---

# Typed requirements are measured

## Why

The requirement value is typed by kind
([a requirement carries a typed value of its kind](../decisions/a-requirement-carries-a-typed-value-of-its-kind.md)),
and attribution, the lifecycle, the drops and the verdict read only typed data
([the requirement lifecycle is derived](../decisions/the-requirement-lifecycle-is-derived.md),
[a verification verdict is computed from the site](../decisions/a-verification-verdict-is-computed-from-the-site.md)).
The extraction was measured per kind on hand-labelled corpus turns as each kind
was built: 39 of 40 fields for percentile, fold change and significance, every
field of the record and data types extracted, 131 of 132 fields for count,
ortholog, text and property. Those labels live in the run directories, not in
the corpus, so no gate holds them, and a classifier change cannot be scored
against them.

## What to do

1. The typed gold set: a new field `ExpectedOutcome.requirements` on the first turn of each
   corpus case that states requirements, each with its kind and typed value,
   scored by field equality. State its size and the pass threshold for typed
   accuracy from the measured runs above.
2. A replay of the saved runs under the new schema that reports the typed
   accuracy against the gold set, the share of requirements read as `untyped`,
   and the share of quotes no researcher message holds.
3. Read the property and text rows of the gold set against the condition named
   in [a requirement carries a typed value of its kind](../decisions/a-requirement-carries-a-typed-value-of-its-kind.md)
   ("What would prove this wrong"), and merge the two kinds if it holds.

## Done when

The corpus holds the typed gold set, the eval scores it with a stated threshold,
and the replay's three shares are recorded in the decision that the numbers
bear on.
