---
type: Decision
title: A budget stop is retried by the system, not the user
description: A FRAME pass that exhausts its call budget after binding at least one new criterion is dispatched again once per turn with a continuation work order, and the stop reaches the Lead as a typed PhaseStop it renders in the ledger. Reporting the stop to the Lead alone, retrying every stop, and retrying without a bound was rejected. A pass after an answered question continues the recorded spec with the question and the answer; re-framing from the whole prompt and matching answers to questions by similarity were rejected.
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
most once per turn (`frame_retried_after_stop`). An edit of a strategy that
holds steps continues as an edit, because an edit owes a disposition for every
criterion the turn began with; the continuation carries the question and the
answer the edit's message closed, and every change an earlier pass stated and
no push applied (`dispatch_context.py::the_edit_the_strategy_owes`), which the
continuation owes a disposition too.

**An answered question continues the frame from the recorded spec.** While the
spec holds a bound criterion and the site holds no step of this thread,
`frame_work_order` briefs the pass with the bound draft, the questions the
answer closed and the answer's words (`TurnMarkers.answered`), so it binds only
what the answer concerns. Any classification of a message closes the
questions open when it arrived (`TurnMarkers.questions_at_arrival`) only when
the message can answer one
(`intent.py::ANSWERING_INTENTS`: an answer, an approval, a denial, an
extension or an edit); a follow-up question, an off-topic message, a context
statement and a memory request leave them open. A consult card closes the ones
a pass asked under that message. A budget retry of a continuation runs the
same order again. A message classified `new_strategy` before the turn framed,
consulted or wrote the strategy drops the open questions and the answer an
earlier classification recorded, and is framed fresh: over a strategy that
holds no step, `take_a_new_request` sets the old request, its draft, its
requirements, its recommendations, its open questions, its build record and
its staleness aside, and a budget retry of that pass continues the fresh
frame. A re-classification after that work sets nothing aside. Over a
strategy that holds steps no frame is offered, and the answer reaches the
edit's work order. An edit over steps no spec states edits the spec those
steps describe (`pre_turn.py::hydrate_spec_from_the_strategy`), and the
refusal of an edit on a thread with no step names only the tools the turn
offers.

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

**Framing an answered turn from the whole prompt.** The pass re-derives every
criterion the draft already binds: after one answered question on plasmodb
(conversation 2cc3e2fd) it re-framed all four bound criteria.

**Matching each answer to its question by similarity.** A card's question is
the Lead's paraphrase of FRAME's, and a typed answer names no question, so a
score would pair them by chance. An answer closes every question open when it
arrives.

**Matching the site's name alone in the reply.** "Saved on VEuPathDB" is an
ordinary true sentence. The check requires a transient state beside the name,
so a reply that reports where the strategy lives passes and a reply that asks
the user to wait does not.
