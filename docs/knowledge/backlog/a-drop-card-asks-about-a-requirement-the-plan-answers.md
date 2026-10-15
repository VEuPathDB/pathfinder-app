---
type: Backlog
title: A drop card asks about a requirement the plan answers
description: The drop card asks about every stated requirement the ledger lists as ungroundable, so it can offer to drop a data type that a bound criterion of the plan answers and that the framing pass did not report.
tags: [frame, ledger, grounding, consult]
generated: { by: claude-code/opus-5.5, at: 2026-10-13T00:00:00Z }
status: proposed
---

# A drop card asks about a requirement the plan answers

## What I did

One turn on the QA FungiDB site, new conversation: "In Neurospora there are
good transcriptomic experiments that explore the circadian rhythm. Can you run
those searches and then identify the orthologs in Aspergillus nidulans? There
might be experiments from other fungal species worth exploring too."

## What I got

Five stated requirements, in order: Neurospora, Aspergillus nidulans,
"transcriptomic experiments" (data type), "circadian rhythm", and "experiments
from other fungal species worth exploring".

FRAME bound two criteria, a Neurospora crassa rhythmic transcript level search
and a map to Aspergillus nidulans, and reported one requirement, `R5`,
`site_has_no_search`. The card asked two questions:

| question | FRAME reported it |
|---|---|
| No search on this site states 'transcriptomic experiments'. Drop it from the request? | no |
| No search on this site states 'experiments from other fungal species worth exploring'. Drop it from the request? | yes, `R5` |

## Why that's wrong

The first criterion is a transcript level search, so the plan answers
"transcriptomic experiments". The card tells the researcher that the site has
no such search and offers to drop a requirement the strategy already meets.

## Why it happens

`requirements_no_search_states` (`ai/lead/frame_requirements.py`) asks about
every stated requirement the derived ledger lists as `UNGROUNDABLE`, beside the
ones the pass reported. Why the ledger lists this data type as ungroundable
while a transcript search is bound is not traced.

## Fix

Not chosen. Trace the grounding of a data type constraint in
`domain/strategy/constraint_grounding.py` against the bound criterion of this
turn first. If the ledger is wrong, fix the grounding. If the ledger cannot
know, the card asks only about what the pass reported.

## What you'd get

One question on the card, about "experiments from other fungal species worth
exploring".
