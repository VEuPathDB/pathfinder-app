---
type: Decision
title: A thread accumulates every requirement its user states, and a clarification adds to that list instead of replacing it
description: `StrategyDomainState.requirements` collects each turn's `UserIntent.explicit_constraints`, deduped on kind AND value so two free-form requirements never collapse. The ledger renders the whole list and a fresh spec's goal is seeded from the original request plus the clarification, so a clarification turn frames from both.
tags: [agents, lead, intent, frame, context]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# The decision

`UserIntent.explicit_constraints` is per message. It was also the only thing
the ledger's constraint section and a fresh FRAME pass ever saw, so a
clarification turn framed from the answer alone.

- `StrategyDomainState.requirements` is the thread's list, oldest first.
  `classify_user_intent` appends this turn's constraints through
  `record_intent`, deduped on `(kind, requested_value)`. It is cleared only by
  a `new_strategy` classification while the live graph holds no step and the
  turn has not framed, consulted or written the strategy, and by
  `clear_strategy`. Both set the whole request aside
  (`StrategyDomainState.set_the_request_aside`: the spec, the requirements, the
  recommendations, the open questions, the original request, the build record
  and its staleness); the clear then records the requirements of its own
  message again. A re-classification before any of that work is the
  classifier correcting itself, so it sets the old request aside like a first
  one; after the work it sets nothing aside, because it would destroy a frame,
  an answered consult or a write the turn already made. A thread has a strategy
  when its live graph holds a step, and nowhere else.
- A message answers the questions open when it arrived.
  `StrategyDomainState.markers_for` copies their texts into
  `TurnMarkers.questions_at_arrival` when the record moves to a new message,
  and any classification in `ANSWERING_INTENTS`, first or later, closes
  exactly those and records them in `TurnMarkers.answered` with the message
  text. A question FRAME or an edit asks later under the same message is not
  in the record, so it stays open through any re-classification and waits on
  the next message. A consult card closes every open question, because it
  answers what a pass asked under that same message.
- A `new_strategy` message answers no open question. The classification that
  sets the old request aside drops the questions, whatever the graph holds,
  and the answer an earlier classification of the same message recorded: they
  were asked about the request the message sets aside.
- A `new_strategy` message over a thread whose graph holds a step keeps
  `original_request` and the requirements until the Lead calls
  `clear_strategy`, which the researcher approves. If the Lead edits the
  standing steps instead, VERIFY's request pin reads the old request followed
  by "The user then clarified: " and the new message. That is the record of
  what the thread's strategy answers.
- `StrategyDomainState.original_request` is the text of the first turn whose
  classification states a request of its own (`new_strategy`,
  `extend_strategy`, `edit_strategy`). A `clarification_response` never writes
  it.
- `ai/lead/derive.py` merges the accumulated list into the constraint section,
  and `InvestigationLedger.render_summary` prints one line per stated
  requirement, so the Lead can see a value it already has and not ask again.
- `ai/lead/dispatch_context.py::framing_goal` seeds a missing spec's goal with
  the original request, then the clarification, so FRAME reads both.

# What was rejected

**Deduping the accumulation by dimension only.** `merge_constraints` collapses
by `ConstraintKind`, which is right for "the latest organism wins" and wrong
for the free-form kind: a motif literal and a distance rule are both
`ConstraintKind.OTHER`, and the second would silently delete the first - the
exact loss the cataloged item reports. `derive.py` therefore keeps
`merge_constraints` for the per-dimension override of the spec's assumed
constraints, then re-adds every stated requirement the collapse dropped.

**Letting only a message's first classification answer.** It kept a question
asked later in the turn open, but a classifier that corrected itself could no
longer answer: "Go with your recommendation" first read as
`follow_up_question` and then as `clarification_response` left FRAME's
question open and recorded no answer. The arrival record keeps the first
property and drops the loss.

**Replacing the requirement list on every turn.** That is the behaviour being
replaced. A clarification states less than the request it answers, so a
replacement loses the request.

**Replacing the request when a new one arrives over standing steps.** The old
steps still answer the old request until the researcher approves a clear. A
request replaced without a clear would pin VERIFY and FRAME to a request the
strategy on the screen does not answer, and nothing would say so.
