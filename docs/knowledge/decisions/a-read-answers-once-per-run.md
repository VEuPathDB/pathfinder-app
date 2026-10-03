---
type: Decision
title: A read answers once per run
description: A toolset wrapper holds the call that answered each listed read for one run, and the same read again fails without running and names that call; the Lead and a framing pass list record reads and a check also lists its strategy reads. A read the site breaks off is one failed call that names the site's status, is not held, and never ends the turn.
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

# A read the site does not answer

A site error or timeout in a read is one failed tool call, never the end of the turn.
`ai/capabilities/site_reads.py::SiteReadFailures` is on the Lead's capabilities over
`READ_ONLY_TOOLS`, the resilience the sub-agents get from `ToolResilience`: a
`WDKError` or `ExternalServiceError` of any status but 401 and 403, an
`httpx.TransportError`, a `ConnectionError` or a `TimeoutError` in a listed read becomes
`ToolFailed` with the site's words and status ("HTTP 502: ... ReadTimeout"). A read with a
deadline raises the same failure itself through `read_in_time`: `get_sample_records` and
`read_step_columns` at 20 s, `read_step_ids` at 20 s for a limited read and 60 s for a
whole listing. Because the failure is raised, `ReadOnceToolset` holds nothing for it and the
same read may run again. An identity refusal (401, 403) is no outage: it propagates to the
turn's error path, which asks the researcher to sign in. A write the site broke off
propagates too. `read_step_ids` with a limit reads through `results.sample_page`, so it
answers the same ordered gene ids as `get_sample_records` at that limit. The sample reads
one record per id, so a limited read takes the sample's cap, `MAX_SAMPLE_LIMIT` (100); a
read with no limit lists up to 5000 ids in pages.

`get_strategy` takes no graph id: the thread holds one graph (`StrategySession.graph`), so
the read-once key is `{summary_only}` and needs no normalizing.

# What was measured

A portal turn read the same five records 43 times in a cycle until the turn budget
stopped it (595,548 tokens, no list), and the next turn read them 37 times. The runtime's
repetition guard counts consecutive identical calls only, so a cycle of five ids never
tripped it. A check re-read samples and the strategy at steps 23/36, 32/38 and 17/37.

# What was rejected

**A per-turn record on `TurnMarkers`.** A resumed run holds the earlier answer in its
history as well, and the loop is a property of one run's context.

**A completed read that says it failed.** A read returning `ok: false` is held as
answered, so the same read cannot run once the site recovers, and the model reads it as an
answer. A trichdb read of five ids from a 5,850-gene union timed out inside the client
("Request failed after retries: " with an empty `httpx.ReadTimeout`), and with no seam on
the Lead the error ended the turn.

**A call cap on `read_gene_record`.** A cap stops a legitimate read of many genes and
ends the turn; the repeat is the waste, not the count.
