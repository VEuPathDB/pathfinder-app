---
type: Decision
title: A read answers once per run
description: A toolset wrapper holds the answer of each read for one run while nothing changes, and the same read again runs nothing, costs no tool call of the budget, and names the call that answered it while the model still sees that answer or carries the answer again once the history elided it; every agent holds every read. A read the site breaks off is one failed call that names the site's status, is not held, and never ends the turn.
tags: [lead, verification, tools, cost]
status: stable
---

# The choice

`ai/tools/toolsets/_read_once.py::ReadOnceToolset` wraps the toolset of the Lead, Explore,
a framing pass, a build pass and a check, and holds every tool of `READ_ONLY_TOOLS`. A
completed call is held by its arguments with its answer (`for_run` gives each run a fresh
record). A call outside the held reads (a write, a sub-agent dispatch, a note) releases
every held read except the `lasting` ones, whose answer no call of the run changes:
`RECORD_READS` for the Lead, Explore and the passes that write, and `CHECK_READS` for a
check, which writes no step. The same read again raises `CallRefused`: it runs nothing,
spends no retry, and is not counted in the run's `tool_calls_limit` (pydantic-ai counts a
call only when it succeeds). When the processed history still holds the first answer whole,
the refusal names that call; when the runtime's elision digested it
(`assistant_core.conversation.history.is_elided`) or compaction folded it, the refusal
carries the answer again, so a model whose context lost the data is never starved. The
elision digest itself does not forbid a second read. A read that failed is not held. A
check's refusals of a record it may not read are `CallRefused` too, and name the sampled id
a versionless id stands for. This wrapper is the one repeat mechanism: the framing tools'
own "already read" notices for a search overview and a parameter read are gone.

# A read the site does not answer

A site error or timeout in a read is one failed tool call, never the end of the turn.
`ai/capabilities/site_reads.py::SiteReadFailures` is on the Lead's capabilities over
`READ_ONLY_TOOLS`, the resilience the sub-agents get from `ToolResilience`: a
`WDKError` or `ExternalServiceError` of any status but 401 and 403, an
`httpx.TransportError`, a `ConnectionError` or a `TimeoutError` in a listed read becomes
`ToolFailed` with the site's words and status ("HTTP 502: ... ReadTimeout"). A library tool
the api calls in process raises a `fastmcp` `ToolError` and keeps the library's words. Its
cause is judged by one rule, `services/site_errors.py::site_status` and `unreached`, the
rule an audit run judges a failed unit by:
- a status of 401 or 403 reaches the turn's error path;
- a transport error, a timeout, or a status of 500 or more is no answer (a `JBrowseError`
  by its upstream status);
- every other cause is a refusal the model reads: an error with the data parsing code (a
  `DataParsingError` or a `TrackReadError`: the site answered with something unreadable),
  a `GenomeIndexError`, a validation error, a status below 500;
- a `ToolError` with no cause is the library's refusal of the arguments.
A WDK reply that does not parse fails the call on every tool of every agent that
carries tools, listed read or not (`unparsed_site_reply`): a pydantic `ValidationError`
whose title names a `WDKModel` subclass, or a `DataParsingError` it caused, becomes
`ToolFailed` naming the tool and the reply model, and charges no retry. A tool in
`READ_ONLY_TOOLS` says nothing was read and the strategy is unchanged; any other tool
says part of its change may already hold on the site and the strategy must be read
again. A `ValidationError` from a model built from the call's arguments stays a
corrective retry.
A read with a
deadline raises the same failure itself through `read_in_time`: `get_sample_records` and
the check's column read at 20 s, `read_step_ids` at 20 s for a limited read and 60 s for a
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

An Explore turn read 76 times and stopped at the 80-call budget: 14 calls repeated an
earlier call's arguments, each returned the whole payload again, and every one of the 14
repeated a result the history had elided under "do not fetch again". The re-read was the
model recovering data it had lost from its context, so an answer that only named the
earlier call would have starved it.

# What was rejected

**A short "you read this" answer for every repeat.** Each of the measured repeats was of an
elided result; the model had no copy of the answer to read.

**A per-turn record on `TurnMarkers`.** A resumed run holds the earlier answer in its
history as well, and the loop is a property of one run's context.

**A completed read that says it failed.** A read returning `ok: false` is held as
answered, so the same read cannot run once the site recovers, and the model reads it as an
answer. A trichdb read of five ids from a 5,850-gene union timed out inside the client
("Request failed after retries: " with an empty `httpx.ReadTimeout`), and with no seam on
the Lead the error ended the turn.

**A call cap on `read_gene_record`.** A cap stops a legitimate read of many genes and
ends the turn; the repeat is the waste, not the count.
