---
type: Backlog
title: The same sample again is the sample the thread showed
description: A request to show an earlier sample again is answered from a fresh read of the step's ids, so two of the five genes differ from the ones the researcher was shown.
tags: [lead, records, samples]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: proposed
---

# The same sample again is the sample the thread showed

**What I did.** On hostdb, corpus case `uat-dry3-d-hostdb`: built Mus musculus
C57BL/6J chromosome 17 genes with GO term 'MHC class I protein complex' (9 genes),
asked for a sample of five, then asked "Can you show me that same sample of five
genes again? I want to copy the IDs."

**What I got.** The third turn listed ENSMUSG00000035929, ENSMUSG00000060550,
ENSMUSG00000061232, ENSMUSG00000067212 and ENSMUSG00000067235. The fourth turn ran
`read_step_ids` and listed ENSMUSG00000035929, ENSMUSG00000060550,
ENSMUSG00000067235, ENSMUSG00000073409 and ENSMUSG00000091705.

**Why that's wrong.** The researcher copies ids for a sample they were shown and
gets two genes they were never shown, with nothing saying the set changed.

**Why it happens.** The seeded sample holds only when the Lead calls
`get_sample_records` again; `StrategyDomainState.shown_record_ids` holds the shown
ids, but no tool or ledger section offers them, so the Lead answers from
`read_step_ids` and picks five of its own.

**Fix.** Offer the shown records to the Lead, in the ledger or as a read, and
have a request for records shown earlier answered from them.

**What you'd get.** The fourth turn lists the same five ids the third turn listed.
