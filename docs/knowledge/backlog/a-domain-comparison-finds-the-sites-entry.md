---
type: Backlog
title: A domain comparison finds the site's entry
description: Asked to compare a name search with a domain search, the Lead asks the researcher for an accession the site already lists.
tags: [lead, frame, vocabulary]
generated: { by: claude-code/opus-5.5, at: 2026-11-05T00:00:00Z }
status: proposed
---

# A domain comparison finds the site's entry

## What I did

Replayed the corpus case `uat-dry3-d-sides-microsporidiadb` on QA MicrosporidiaDB, on Luna,
through the worker. The second message asks whether an InterPro or Pfam search for the polar tube
protein family finds more E. bieneusi H348 genes than the name search.

## What I got

Five of six runs ended on a card. One reply said:

> I need the specific InterPro or Pfam family entry

The site lists `PF17022 : Polar tube protein 2 from Microsporidia`. The one run that reached it
counted 1 gene, `EBI_26400`, the same gene as the name search.

## Why that's wrong

The question goes unanswered and the researcher is asked for a value the site holds. No count
is wrong.

## Why it happens

Reading a parameter's vocabulary is FRAME's: `get_parameter_options` is not a Lead tool, and
`frame_problem` runs only while the strategy holds no step. The Lead sees entries only when a
`count_search` refusal names the nearest ones, which takes the right parameter with a wrong value.

## Fix

Not built. Candidate: a read-only FRAME lookup the Lead calls for a comparison, then counts what it
returns. Adding the nearest entries to the wrong-parameter refusal was tried and dropped: the runs
gave up before that refusal, on an empty parameter or with no call at all.

## What you'd get

The comparison in every run, 1 gene against 1 gene, and no card.
