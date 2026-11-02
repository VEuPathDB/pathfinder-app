---
type: Decision
title: An open card docks on the composer
description: A card that waits on the researcher draws above the composer input, one at a time, and the thread keeps only the record of an answered card. Typed words answer the current question of a docked consult as its free-text answer; under any other card they are sent as the next message, which the Lead already reads as the answer. A decline that carries the typed words as its reason was rejected.
tags: [frontend, approvals, consult, composer]
generated: { by: claude-code/opus-5, at: 2026-11-02T00:00:00Z }
status: stable
---

# What was decided

A card is open while its tool part is in `approval-requested` and no user message follows its
message. `openCards` (`apps/web/src/features/conversation/content/parts/cardAnswers.ts`) is the
one reader of that rule.

- **The dock.** The composer draws the first open card above its input
  (`composer/DockedCardView.tsx`), capped at half the viewport with its own scroll, so the input
  stays on screen inside a site's frame. A consult shows one question at a time with its place
  ("1 of 3"). The thread draws nothing for an open card; an answered card keeps its record where
  the call sits (`ConsultRecord`, the decided proposal and separation cards, the decision line of
  `ApprovalCard`). A reloaded thread derives both from the replayed parts.
- **Typed words under a consult.** The input stays enabled and asks for the researcher's own
  answer. The words become the `note` of the current question with no option picked, and the
  dock moves to the next open question; once every question holds an answer, the card is
  submitted through `handleConsultSubmit`. Words that start with a slash are a command, not an
  answer, and go to the commands as they do with no card open. The api takes a note-only answer to any question kind:
  `_answer_requirement` states the note as the requirement when no label is picked
  (`apps/api/src/pathfinder/ai/lead/lead_consult.py`).
- **Typed words under any other card.** They are sent as the next message. `answer_to_the_offer`
  (`apps/api/src/pathfinder/ai/graph/_lead_offers.py`) reads a typed approval phrase as a yes,
  and declines the card on any other words and hands them to the Lead as its next user prompt.

# What was rejected

- **A decline with the typed words as its reason.** The reason reaches the Lead, but worse than
  a message does. On an offer card a decline ends the turn with no model call and stores the
  words only as the declined proposal's note, so the researcher gets no reply. A typed "yes"
  would become a no, where a message is read as a yes. The words would also not appear in the
  thread as the researcher's message.
- **The card inline in the thread with a louder style.** It still scrolls away from the input
  the researcher is looking at.
