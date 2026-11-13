---
type: Decision
title: A message is read before the Lead runs
description: Each researcher message is read once before the Lead's run, by two Decisions views and a quote extraction call, into a typed reading and a stated request the turn's intent is derived from; the Lead's classify tool, its refusal loop and a mid-turn re-read were rejected.
tags: [lead, intent, classification, decisions, requirements]
generated: { by: claude-code/opus-5.5, at: 2026-11-02T00:00:00Z }
status: stable
---

# What was decided

`ai/graph/_lead_reading.py::read_the_words` runs in `lead_node._drive_lead_stream` after
the turn's resumption is resolved and before the Lead's first request. It reads the
turn's new message, or on a turn that resumes a consult card the free-text notes of its
answers, and nothing on a turn with no words (a durable result, a card click).

`ai/lead/message_reader.py::read_message` runs, in one wait:

- Two Decisions views (`veupathdb_mcp.catalog.decide`, gpt-6-luna), the conversation first
  and the latest message first. Each asks `effect` (none, new, add, change, remove, undo),
  `wants` (12 values) and `edit_direction`; the first also asks the flags (disputes the
  result, audit, remember, context only, off topic) and, only when the typed state holds an
  open question or a waiting card, whether the message answers it. Effect and wants are the
  views' averaged probabilities.
- One extraction call on the Lead's model for the turn (`StatedRequest`): each requirement
  as a verbatim quote of the message with one of eleven kinds, its value and whether it is
  hard; each withdrawal with the number of the held requirement it takes back, from the
  numbered list only this call reads; the goal, the asks, the comparison
  sides, the step ids, the gene ids and the controls. A quote the message does not hold is
  refused once with the quotes named; one still outside the message is dropped.
- A model reading of effect, wants and the flags (`message_reading.md`), started with the
  other calls and used when the top probability of effect or wants is below 0.6, or when
  no Decisions answer came; otherwise it is cancelled.

The guide describes Strategist as a research partner for the pathogens, hosts and vectors the
sites cover as well as a strategy builder. `off_topic` is only a message unrelated to that
biology, the literature and methods about it and the sites' data, strategies and analyses, so a
literature question about a covered pathogen is in scope even when no site record answers it.

`ai/lead/message_intent.py::intent_of` derives the `UserIntent` every consumer already
reads: audit, remember, context only, off topic and answers-open name the classification
in that order, else the effect does; a withdrawal on a message whose effect is none is a
removal. `ai/lead/held_intent.py::hold_the_intent` then completes organisms against the
site's list, drops gene ids neither the message, the records shown last nor an attached
file of the site holds, maps each withdrawn number to the id the thread holds it under,
and records the intent.
The Lead reads the result in its pinned User Intent: the classification, what the message
asks to be told, each stated and withdrawn requirement with its quote, the asks and the
named ids.

A mock deployment reads no message: each arc of the scripted model declares the intent its
messages carry (`ai/models/mock/reading.py::scripted_intent`).

# Why

On the held-out half of 182 labelled turns from the eval corpus, the reading told a
change from no change on 96.0% against 91.0% for the classify tool, read effect and wants
both right on 87.1%, and answered the open-question flag on 100%. The extraction's
quoted requirements were 88.7% precise against 68.8% for the classify tool's constraints,
and every quote is a substring of the message by construction. Two replays of all 182
turns through the wired reader held those figures (98.5% and 97.0% on change or no change
on the held-out half, extraction precision 92.7% and 91.4%). The gain is accuracy, not
time: the reading takes 4.0 s at the median and 6.9 s at the 90th percentile, against
3.45 s for a classify call made without the Lead's instructions, and costs about $0.0009
a turn. The extraction call bounds it; at low reasoning it is a second faster but its
precision falls from 90% to 74%, so it runs at the model's default. The model reading
starts with the other calls and is cancelled when Decisions settles, so a turn that falls
back waits 4.6 s at the median instead of 8.0 s.

The checks the classify tool refused are facts of the reading: a question cannot ask a
change, because effect and wants are separate answers; a message cannot answer a question
no one asked, because the question is put only when one is open; a quote cannot be
invented. Ids the turn does not hold are dropped, not refused, so no refusal loop remains.

# Rejected

**Keeping a classify tool on the Lead.** Its description had grown to 1,372 words of
routing rules, and 40 of 45 recorded refusals refused the Lead's own reclassification.
A tool the Lead calls first costs a full Lead request on every turn.

**A Lead tool to read the message again mid-turn.** No measured run needs it. A card's
note is read when the card resumes.

**A concise model reading alone.** It read 94.5% of changes but 84.6% of effect and wants
together, and took about three seconds longer than Decisions.

**One Decisions predicate per category.** About 78% on the same turns; the categories
overlap, and a choice question makes them exclusive.

**A combination kind in the extraction.** How requirements combine is read from FRAME's
tree against the researcher's words, not written by a model as a requirement
([operators come from FRAME's tree](operators-come-from-frames-tree.md)). A value the
message adds beside a held one of the same kind names that requirement's number in
`beside`, so it does not replace it.
