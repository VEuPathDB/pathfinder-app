---
type: Backlog
title: A typed reply over the readings card keeps its readings
description: Words typed over Explore's readings card take one of two paths, the Lead's typed-reply path at the API and a card answer with a note in the web, and neither path builds a counted reading; record a run of each path and decide whether the web sends typed words over a card that takes no note as a new message.
tags: [modes, explore, hand-over, intent, requirements, web]
generated: { by: claude-code/opus-5.5, at: 2026-11-06T00:00:00Z }
status: proposed
---

# A typed reply over the readings card keeps its readings

## What is known

Explore ends a turn on its readings card, which parks for the Lead. When the card parks,
`ai/graph/_explore_turn.py::hand_over_reading` records the card's labels as one named reading.
The researcher can type words over the card instead of picking. Those words take one of two
paths. No run has recorded either path yet; both are read from the code.

**At the API (a client or the devtools sends a new message).** The route node sends the typed
message to the Lead, because the card is parked under the Lead's phase
(`ai/graph/route_node.py::parked_route`). The Lead reads it on its typed-reply path. When the
message reader classes it `new_strategy` and the turn has not framed or consulted,
`ai/lead/held_intent.py` calls `take_a_new_request`. On a thread with no step, that calls
`set_the_request_aside`, which empties `named_readings`, `request_messages` and the open
questions. FRAME then frames from the typed message alone, and the counted readings are not
its starting point.

**In the web.** Typed words over any open consult card become an answer to that card, with
the typed text as the note (`apps/web/src/features/conversation/composer/useDockedCard.ts`,
`answerTyped`, and `typedAnswer` in
`apps/web/src/features/conversation/content/parts/consultDraft.ts`). This holds also for the
readings card, whose question sets `allowNotes` to false. The Lead's consult path
(`ai/lead/lead_consult.py`) records the note as request text and as a requirement, and picks
no reading, because the answer names no label.

## What to do

1. Record a run of each path with the mock arc `[[arc:explore]]`: a typed message sent through
   the API, and a typed note sent as a card answer the way the web sends it. Then repeat both
   on QA with the real message reader.
2. Decide whether the web sends typed words over a card with `allowNotes` false as a new
   message instead of a card answer.
3. Decide how the Lead keeps the counted readings for a typed reply. Options: the reader's
   open-question flag covers the readings card, so a reply to it reads as an answer; or
   `take_a_new_request` keeps the named readings while a readings card is open.

## Done when

A typed reply over the readings card that names a reading builds that reading with the stated
change, the named reading stays in the ledger, and a test pins each path.
