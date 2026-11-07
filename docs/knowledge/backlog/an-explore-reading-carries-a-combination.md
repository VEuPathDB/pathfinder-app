---
type: Backlog
title: An Explore reading carries a combination
description: A request with two criteria, such as 7-TM proteins with no ortholog in other Diptera, reaches Build as one search because a reading is one catalog search, and the readings card can offer the two halves as alternatives; let a reading carry a combine and refuse a card whose options are parts of one request.
tags: [explore, readings, consult]
generated: { by: claude-code/opus-5.5, at: 2026-11-07T00:00:00Z }
status: proposed
---

# An Explore reading carries a combination

## What I did

Sent `Find classic 7-TM membrane proteins in Anopheles gambiae that do not have close orthologs
in other genera of Diptera.` in Explore on the dev portal, six fresh runs with no memories:
three on GPT-5.6 Luna and three on GPT-6.1 Terra, medium effort, on 2026-11-07.

## What I got

- Five runs counted one reading, `GenesByTransmembraneDomains` with `min_tm` 7 and `max_tm` 7:
  219 genes on *A. gambiae* PEST in four, 425 on every *A. gambiae* genome in one. Each reply
  said the orthology criterion was not applied and should be intersected in Build.
- One Luna run counted two readings, the 7-TM search (219) and `GenesByOrthologPattern` absent
  from Drosophila, and parked the readings card with the two as options: "Which reading should
  Build create?"
- No run counted a Pfam domain reading. Terra read `GenesByInterproDomain` in all three runs and
  named a GPCR domain filter as a refinement only.

## Why that's wrong

The request has two criteria. The hand-over gives Build half of it, and the card asks the
researcher to choose between the halves, so either pick builds a set that does not answer the
question.

## Why it happens

`propose_readings` (`ai/explore/explore_tools.py`) takes each reading as one catalog search
with its parameter values, so a reading cannot state a combine, and `readings_card.py` admits
any counted labels as alternatives.

## Fix

Let a reading be a small step tree (searches and one combine) that `propose_readings` counts
whole, and refuse a readings card whose options are the parts of one counted combination.

## What you'd get

One reading, `7-TM INTERSECT absent from other Diptera`, with its count, and a Build it button
that builds both steps.
