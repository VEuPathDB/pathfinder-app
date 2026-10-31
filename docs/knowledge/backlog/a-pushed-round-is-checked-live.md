---
type: Backlog
title: The last pushed round is checked live
description: No live turn has yet had a build refused, so the resent-build bound is not seen live; the gene-certainty follow-up of an audit is deferred while the audit assistant does not ship.
tags: [audit, orthomcl, live]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# The last pushed round is checked live

## What is open

- **A refused build is not resent unchanged.** `RefusalMemoryToolset`
  (`ai/tools/toolsets/_refusals.py`) answers a call refused once and sent again with the
  same arguments, with only reads between, with the refusal and does not run it. The unit
  tests hold it. Live on QA on 2026-10-31, eight Lead turns (the five S2 cases, the OrthoMCL
  singleton ranking and both turns of `uat-n13-plasmodb`) and their sub-agents sent 226 tool
  calls and the toolset refused none: each turn called `build_strategy` at most once and it ran, and the
  second turn of `uat-n13-plasmodb` replaced the strategy through `propose_changes`. The
  bound is seen live only on a turn whose build is refused.
- **Deferred: an audit follow-up names a gene's own certainty.** The gene-model audit
  assistant does not ship to QA, so this check waits for it. On 2026-10-26 a request that
  named only genes made the Lead pass the site name as a genome to the audit planner, not
  retry after its refusal, and answer from the investigator; facts rendered as bare values
  in prose ("no RNA-seq junction support 0", "preserves the reading frame yes").

## Done when

A live turn whose build is refused does not send the same build again with only reads
between; and, once the audit assistant ships, a live audit follow-up names a gene's own
certainty.
