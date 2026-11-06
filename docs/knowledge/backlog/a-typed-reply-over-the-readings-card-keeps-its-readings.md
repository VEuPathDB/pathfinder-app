---
type: Backlog
title: A typed reply over the readings card keeps its readings
description: When the researcher types a reply over Explore's readings card instead of picking, and the message reader classes it new_strategy on a thread with no step, the Lead sets the request aside and the card's named readings go with it; not yet reproduced in a run.
tags: [modes, explore, hand-over, intent, requirements]
generated: { by: claude-code/opus-5.5, at: 2026-11-06T00:00:00Z }
status: proposed
---

# A typed reply over the readings card keeps its readings

## What I did

Read the code path only; no run reproduces it yet. Explore ends a turn on its readings card,
parked for the Lead. When the card parks, `ai/graph/_explore_turn.py::hand_over_reading`
records the card's labels as one named reading. The researcher then types a message over the
card, for example "build the first one, but only for the blood stages", instead of picking.

## What I got

Expected from the code, not observed: the route node sends the typed message to the Lead,
because the card is parked under the Lead's phase. The Lead reads the message. When the reading
classes it `new_strategy` and the turn has not framed or consulted,
`ai/lead/held_intent.py` calls `take_a_new_request`. On a thread with no step that calls
`set_the_request_aside`, which empties `named_readings`, `request_messages` and the open
questions.

## Why that's wrong

The readings the researcher was looking at, with their counts, are gone from the state Build
reads. FRAME frames from the typed message alone, and the readings Explore counted are not
offered as the starting point.

## Why it happens

`StrategyDomainState.take_a_new_request` (`ai/graph/state.py`) treats every `new_strategy`
message on an empty thread as a request that replaces the old one. It does not know that the
open card holds readings this message answers.

## Fix

Not decided. Reproduce it first with the mock arc `[[arc:explore]]` and a typed reply in a
recorded run, then on QA with the real reader. Options: the reader's open-question flag
covers the readings card, so a reply to it is read as an answer; or `take_a_new_request` keeps
the named readings while a readings card is open.

## What you'd get

A typed reply over the card that names a reading builds that reading with the stated change,
and the named reading stays in the ledger.
