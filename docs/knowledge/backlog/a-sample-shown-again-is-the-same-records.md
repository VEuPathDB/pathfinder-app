---
type: Backlog
title: A sample shown again is the same records
description: Asked to show the same sample of five genes again, the Lead reads the first five ids of the step instead of the five it showed, so the researcher copies a different list.
tags: [lead, records, sample]
generated: { by: claude-code/opus-5.5, at: 2026-11-02T00:00:00Z }
status: proposed
---

# A sample shown again is the same records

## What happens

Corpus case `uat-dry3-d-hostdb`, replayed on QA HostDB with Luna on 2026-11-02. Turn 3,
"Put it back to chromosome 17 and show me a sample of five genes from the result.", ran
`get_sample_records` with limit 8 and showed ENSMUSG00000035929, ENSMUSG00000060550,
ENSMUSG00000061232, ENSMUSG00000067212 and ENSMUSG00000067235. Turn 4, "Can you show me
that same sample of five genes again? I want to copy the IDs.", ran `read_step_ids` with
limit 5 and showed ENSMUSG00000035929, ENSMUSG00000060550, ENSMUSG00000067212,
ENSMUSG00000073411 and ENSMUSG00000079507: the first five ids of the 9-gene step, three of
them not shown before. The reply calls them the same sample.

## Done when

A record list a turn showed can be shown again from what the thread recorded of that turn
(`domain/record_facts`), not read again from the site; the case passes its
`sameRecordsAs` check in a live replay.
