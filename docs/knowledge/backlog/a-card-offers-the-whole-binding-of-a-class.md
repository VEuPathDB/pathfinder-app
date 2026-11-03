---
type: Backlog
title: A card offers the whole binding of a class
description: When FRAME bound several entries for a requirement that names a class and the vocabulary pick is unsettled, the card offers single entries and may recommend one; keep the question and add one option that holds everything FRAME bound, with its measured count. Held until a re-measure shows it matters.
tags: [frame, consult, vocabulary, decisions]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: proposed
---

# A card offers the whole binding of a class

## What happens

An unsettled vocabulary pick reopens a value FRAME bound
(`ai/agents/frame_pick_checks.py::hold_an_unsettled_pick_to_a_question`,
`domain/strategy/vocab_picks.py::spec_held_open`). When FRAME bound several entries for a
requirement that names a class, the card offers only single entries and may recommend one.
A researcher who accepts the recommendation gets one entry where the requirement names the
class, and no option states what FRAME measured.

## Proposed

Keep the question. Add one option that holds everything FRAME bound, with its measured count.

The question stays the way the spec stays open:
[an unsettled vocabulary pick is asked](../decisions/an-unsettled-vocabulary-pick-is-asked.md)
rejected keeping the binding beside the question, and this item does not reopen that. The
entries leave the binding until the card answers; the new option only offers them again as
one answer.

## Why it is held

In the last measurement, 4 of 123 corpus cases reached this card. Two of those 4 ask which
domain states an organism name, which may be another cause. Do this only if a re-measure
shows it matters.

## Done when

A re-measure of the corpus counts the cases that reach this card with a binding of several
entries for a requirement that names a class. If the count still justifies the change, the
option is on the card with its count and a test holds it; if not, this item is removed.
