---
type: Decision
title: A read answers once per run
description: A toolset wrapper holds the call that answered each listed read for one run, and the same read again fails without running and names that call; the Lead and a framing pass list record reads and a check also lists its strategy reads.
tags: [lead, verification, tools, cost]
status: stable
---

# The choice

`ai/tools/toolsets/_read_once.py::ReadOnceToolset` wraps the Lead's own toolset, the
framing pass's toolset and the check's toolset. For each tool it lists, a completed call is held by its arguments for the
run (`for_run` gives each run a fresh record); the same call again fails with
`ToolFailed`, names the call that answered it and spends no retry. A read that failed is
not held. The lists live beside the guard vocabulary (`ai/agents/tool_vocabulary.py`):
`RECORD_READS` for the Lead and a framing pass, whose edits change what a strategy read returns, and
`CHECK_READS` for a check, which writes no step. A check's refusals of a record it may not
read are `ToolFailed` too, and name the sampled id a versionless id stands for.

# What was measured

A portal turn read the same five records 43 times in a cycle until the turn budget
stopped it (595,548 tokens, no list), and the next turn read them 37 times. The runtime's
repetition guard counts consecutive identical calls only, so a cycle of five ids never
tripped it. A check re-read samples and the strategy at steps 23/36, 32/38 and 17/37.

# What was rejected

**A per-turn record on `TurnMarkers`.** A resumed run holds the earlier answer in its
history as well, and the loop is a property of one run's context.

**A call cap on `read_gene_record`.** A cap stops a legitimate read of many genes and
ends the turn; the repeat is the waste, not the count.
