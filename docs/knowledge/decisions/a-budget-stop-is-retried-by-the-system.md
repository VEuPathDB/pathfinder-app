---
type: Decision
title: A budget stop is retried by the system, not the user
description: A FRAME pass that exhausts its call budget after binding at least one new criterion is dispatched again once per turn with a continuation work order, and the stop reaches the Lead as a typed PhaseStop it renders in the ledger. Reporting the stop to the Lead alone, retrying every stop, and retrying without a bound was rejected.
tags: [agents, lead, frame, budget, ergonomics]
generated: { by: claude-code/opus-5, at: 2026-09-01T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# What was decided

A sub-agent that hits its usage ceiling used to be logged and dropped:
`stream_sub_agent` returned `None`, `run_frame` reported whatever the partial
draft held, and the Lead read unbound criteria with no record of why. Nothing
in the turn stated the cause, so the reply invented one and told the
researcher to wait for VEuPathDB.

**The stop is typed data.** `PhaseStop` names the pass, the reason
(`budget` or `repeated_call`), the calls it spent, and the criteria it bound
against the count it was sized for. `stream_sub_agent` records it on
`LeadDeps.last_phase_stop` on both stop paths and clears it when the next
dispatch starts, so a later clean pass never inherits an earlier stop. The
ledger carries it and `render_summary` names it, which is the text the Lead
reads before it answers.

**A budget stop that made progress is continued by the dispatch.** When the
pass bound a criterion it did not start with, `run_frame` dispatches once more
with a continuation work order that prints what is bound and asks only for the
rest, sized by the same `criteria_floor` the first pass used. The retry runs at
most once per turn (`frame_retried_after_stop`). A turn that started from a
strategy continues as an edit, because an edit owes a disposition for every
criterion the turn began with. A pass that continues an answered question is a
continuation too: while the spec holds a bound criterion and no build,
`frame_work_order` briefs it with the bound draft, the questions the message
answers (`TurnMarkers.answered_questions`) and the answer, so it binds only
what the answer concerns.

**A reply may not attribute a stop to VEuPathDB.** `blamed_the_site` is a pure
check over the reply text and the ledger's build section: text naming the site
together with a transient state, while no step failed and no step came back
empty, is refused by an output validator on the Lead and the refusal hands it
the real stop to write. It fires once per turn.

# What was rejected

**Reporting the stop to the Lead and stopping there.** The Lead would state the
cause correctly and still ask the user to re-request a pass the system can run
itself. A budget is the product's own number; spending the user's turn on it is
the product's job.

**Retrying every stop.** A pass that bound nothing repeats itself: the same
goal, the same budget, the same result. That case is already reported through
`frame_result_from_draft`, and a repetition stop is a loop the guard ended, so
neither is retried.

**Retrying until the spec is ready.** One retry is bounded by construction. A
loop over "not ready yet" spends the whole turn on a goal that may be too large
for any budget, and the Lead cannot ask the user a question while it runs.

**Matching the site's name alone in the reply.** "Saved on VEuPathDB" is an
ordinary true sentence. The check requires a transient state beside the name,
so a reply that reports where the strategy lives passes and a reply that asks
the user to wait does not.
