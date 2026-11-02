---
type: Backlog
title: A suggested prompt is measured before it ships
description: Every offered suggestion has one recorded passing run on its QA site; what remains is a reviewable file in which biologists propose candidates, each offered only after its recorded run meets the stated expectation.
tags: [suggested-prompts, first-run]
generated: { by: claude-code/opus-5, at: 2026-10-20T00:00:00Z }
status: proposed
---

# A suggested prompt is measured before it ships

## What happens

`apps/web/src/features/conversation/data/suggestedQuestions.json` holds 49
suggestions. Each one was run once on its QA site and builds a strategy, or a PCA,
that meets every constraint the question states (see the 2026-10-31 entry in the
[log](../log.md)). The file is still edited by hand, in code, and nothing stops a
new suggestion from shipping without a run.

## Change

Biologists propose the example questions: each site's candidates live in one
reviewable file with the question, the answer a biologist expects (the record type,
the constraints, roughly how many results), and who may edit it. Each candidate
becomes an eval case (`evals/corpus/`) and is offered only after its recorded run
meets the stated expectation; a candidate that fails stays in the file with its
measured outcome, so the proposer sees why.

## Done when

A biologist can add a candidate without a code change, and only candidates with a
recorded passing run are offered.
