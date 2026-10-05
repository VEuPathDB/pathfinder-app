---
type: Backlog
title: A message that commands a change is an edit when it also asks a question
description: A message that commands a change and asks what it does can be classified a follow-up question that withdraws nothing, so the turn answers read-only and the change is never made.
tags: [lead, classification, edit]
generated: { by: claude-code/opus-5.5, at: 2026-10-05T00:00:00Z }
status: proposed
---

# A message that commands a change is an edit when it also asks a question

**What I did.** On hostdb, corpus case `uat-dry3-d-hostdb`: built Mus musculus
C57BL/6J chromosome 17 genes with GO term 'MHC class I protein complex' (2,268
location genes, 9 in the intersection), then sent "Change the chromosome to 19.
How does the count change?"

**What I got.** The classification was a follow-up question with
`asks=["How does the count change?"]` and nothing withdrawn. The turn ran
`compare_search_variants` and answered with the chromosome 19 count (1,372); the
facts still show chromosome 17 and a root of 9.

**Why that's wrong.** The researcher asked for the strategy to move to
chromosome 19 and reads a count for a change the strategy does not hold.

**Why it happens.** `classification_gate.classification_refusal` refuses a
question that withdraws a requirement (`question_withdraws_message`); a question
that withdraws nothing passes, though words outside its asks command the change.

**Fix.** Refuse a follow-up question whose message commands a change outside its
asks. The reading has to tell a command ("change the chromosome to 19") from a
remark beside a question ("thanks", "that seems high"), so it is designed against
the corpus cases that hold a remark before a question.

**What you'd get.** The turn edits the location step to chromosome 19 and the
facts show "0 genes, 9 genes before this turn's edit".
