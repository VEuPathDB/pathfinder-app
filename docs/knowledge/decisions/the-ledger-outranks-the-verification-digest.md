---
type: Decision
title: The ledger outranks the verification digest, and the contradiction is corrected where the digest is recorded
description: run_verification refuses a success digest the ledger's build section does not support and rewrites it into a failure digest naming the contradiction. A ModelRetry on the verification sub-agent was rejected, because retries are finite and the flag also decides the memory auto-write and the eval verdict. The digest is the verdict while the strategy holds the revision it judged; clearing it on each new message was rejected.
tags: [verification, ledger, trust, agents]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# What was decided

`ai/lead/ledger.py::build_contradiction` states, in one place, why a success
verdict cannot stand over a build: the build ran and did not come out clean
(a step failed, was skipped, or returned nothing), or no build ran this turn
and no step of the strategy is in VEuPathDB. `digest_held_to_the_build`
rewrites the digest when it does: `success` becomes False, `reason` and
`prose` name the contradiction, and the original prose is kept below it so
nothing the checker found is lost.

`ai/lead/verify_dispatch.py::run_verification` applies both before it
records the digest with `StrategyDomainState.record_verdict`. That is the
single write point, so
the three readers of the flag - the delta the Lead quotes, the memory
auto-write in `ai/graph/nodes.py`, and the eval extractor's verdict in
`services/eval_data/chunk_reader.py` - all read the corrected digest.

The rule reads the ledger and the live session only. The digest may add
detail to what the build recorded; it may never overrule it.

# The verdict belongs to the strategy revision it judged

`record_verdict` keeps the digest with `verified_revision`, the
`domain/strategy/revision.py::strategy_revision` of the live tree the check
read. `PipelineState.turn_verdict` returns the digest while
`strategy_revision(answered_graph)` still equals it, and None otherwise.
`answered_graph` is the tree the strategy holds after every write of the thread
(a build, an edit, a delete, a clear, an EDA export) and after the refresh every
turn starts with, so its revision is the live one. Every reader takes the
digest through `turn_verdict`: the ledger
(`derive.py::_derive_verification_section`), the budget stop report, the memory
auto-write and its candidates, and the eval runner's `checkpointed_verdict`.

A question about the strategy, a resumed turn and a durable completion turn
change nothing, so they keep the verdict. A write that changes what the
strategy computes blanks it until a check of the new revision. The memory
auto-write and the scratchpad compaction in `finalize_turn` read the verdict
only in the turn that ran the check (`turn_markers.verification_dispatched`):
a standing verdict is the strategy's, not a later turn's finding. The revision
hashes the inputs only (searches, parameters, operators, shape), so a count
read again or a WDK id assigned never moves it.

Three other rules were rejected. **Clearing the digest on each new user
message** blanked the Verification tab for a strategy nothing had changed: a
follow-up question after a verified build showed `complete: False` and
`successful: False`. Clearing the digest on each write needs a hook on every
path that writes the strategy, and the next new path forgets it; the revision
reads the tree those paths already record. Gating each reader on
`turn_markers.verification_dispatched` puts one rule in five places, as the
section below already rejects for the build contradiction.

# What was rejected

**A `ModelRetry` from the verification tool.** Handing the contradiction back
to the sub-agent and asking it to try again is the more conversational fix,
and it lets the model explain itself. It was rejected because it does not
make the contradiction impossible: retries are finite, and a model that
misread its input once will usually misread it again, after which the wrong
flag lands anyway. It also spends a second sub-agent run to reach a verdict
the ledger already holds.

**Correcting each reader.** The reply, the auto-write and the eval extractor
could each check the build themselves. That puts one rule in three places and
guarantees that the next reader of the flag forgets it.

**Deriving the whole verdict from the ledger and dropping `success`.** The
digest carries findings a ledger cannot: sample records, control tests,
constraint reports. Removing the flag would lose them. The flag is kept and
bounded instead.

# The consequence, stated

One screen can no longer say "build - failed" and "Verified end-to-end." at
the same time. A verification that claims more than the build supports is
reported as the build failure it is, and nothing is remembered from it.
