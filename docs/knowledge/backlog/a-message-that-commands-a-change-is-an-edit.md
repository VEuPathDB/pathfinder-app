---
type: Backlog
title: A message that commands a change is an edit when it also asks a question
description: A message that commands a change and asks what it does was answered read-only; the classifier now flags a question that asks a change and the gate sends it to framing, and one live replay of uat-dry3-d-hostdb remains.
tags: [lead, classification, edit]
generated: { by: claude-code/opus-5.5, at: 2026-10-05T00:00:00Z }
status: proposed
---

# A message that commands a change is an edit when it also asks a question

## What happened

On hostdb (corpus case `uat-dry3-d-hostdb`), after a strategy of Mus musculus C57BL/6J
chromosome 17 genes with GO term 'MHC class I protein complex' (9 genes), the message
"Change the chromosome to 19. How does the count change?" was classified a follow-up
question that withdrew nothing. The turn answered with the chromosome 19 count (1,372)
and the strategy still held chromosome 17.

## Where it stands

The classifier sets the typed `UserIntent.asks_a_change` (`ai/lead/intent.py`), and
`classification_gate.classification_refusal` refuses a follow-up question that sets it,
so the turn goes to framing (`tests/unit/ai/lead/test_a_question_that_asks_a_change_reaches_framing.py`).
No recorded run of the case has followed the change.

## Done when

A live replay of `uat-dry3-d-hostdb` on QA edits the location step to chromosome 19 and
the facts show "0 genes, 9 genes before this turn's edit".
