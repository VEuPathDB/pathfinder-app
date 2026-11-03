---
type: Backlog
title: Two cases answer the cards the Lead now asks
description: Two cases leave the consult cards the Lead now asks unanswered, so they end before a build.
tags: [evals, corpus, markdown, cards]
generated: { by: claude-code/opus-5.5, at: 2026-11-02T00:00:00Z }
status: proposed
---

# Two cases answer the cards the Lead now asks

## What happens

`uat-dry4-b-tritrypdb` and `uat-dry-b-fungidb` run under the `leave` policy. The Lead now
asks a consult card for the zinc-finger domain entry (turns 1 and 2 of dry4) and for the
anchored-membrane GO term (turn 5 of fungidb). The cases name no answer for those cards,
so dry4 builds no strategy and fungidb keeps one step where the case expects
`(GenesByGoTerm INTERSECT GenesByOrthologPattern)`. Both fail the same way on main and on
the requirement-id branch.

## Done when

dry4 and fungidb name an answer for each card the Lead asks, recorded from a run; a corpus
replay passes both.
