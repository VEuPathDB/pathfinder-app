---
type: Backlog
title: A phrase in an OR search stays a phrase
description: Asked to broaden a text search with OR, the strategy runs the phrase as separate words, so a result that should hold 86 genes holds 279. Fix before prod.
tags: [frame, text-search, counts, before-prod]
generated: { by: claude-code/opus-5.5, at: 2026-11-05T00:00:00Z }
status: proposed
---

# A phrase in an OR search stays a phrase

Fix before prod live. It does not hold QA.

## What I did

Replayed the corpus case `uat-dry-b-giardiadb` on QA GiardiaDB, on Luna, through the worker. The
last message asks to broaden the first step so it also catches genes whose product is just VSP,
keep the signal peptide filter, and state both counts. Then measured each search term on QA
GiardiaDB, build 71, in the product field of Giardia Assemblage A isolate WB.

## What I got

| Search term | Genes | With a signal peptide |
|---|---|---|
| `variant-specific surface protein OR VSP` (run by the strategy) | 6,093 | 278 |
| `variant-specific surface protein* OR VSP` (run by the strategy) | 6,100 | 279 |
| `"variant-specific surface protein" OR VSP` (what was asked) | 216 | 86 |

Three more runs ended on 323, 279 and 355 genes. All three still pass the case.

## Why that's wrong

The genome holds 355 signal peptide genes, so a result of 279 is most of them, not the VSP
subset. Sampled records included thioredoxin and leucine-rich repeat proteins. A count in a
figure or a saved set would be about three times too large. At least two of the last three
replies warned that the search was broad, and the wrong count still stood.

## Why it happens

`set_criterion` takes `text_expression` as text FRAME writes in the site's search syntax, and FRAME
writes the phrase without quotes, so the site matches any of its words, including "protein".

## Fix

Not built. Candidate: FRAME passes the terms as a list and the code writes the site's syntax, so
the unquoted form cannot be written. Expressions already stored as text need a reading. Two
approaches failed and were dropped: holding the turn open on a sampled record judged "no" never
fired in three runs, because VERIFY judged every record "yes" or "unclear".

The case also needs to pin 216 and 86. It checks no count today, so its pass says nothing about
this bug.

## What you'd get

216 genes, 86 with a signal peptide, in every run.
