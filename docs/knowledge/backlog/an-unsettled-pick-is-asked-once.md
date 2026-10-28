---
type: Backlog
title: An unsettled vocabulary pick is asked once, and always
description: On QA a Decisions pick that was not settled was asked as two questions on one card, and a pick over six entries that was not settled was bound without a question.
tags: [frame, decisions, cards]
status: proposed
---

# What is wrong

- One card held FRAME's pick question and a second Lead question that asks the same choice.
- A pick with confidence 0.26 (not settled) over Pfam entries was bound to eleven entries with no question.

# Done when

An unsettled pick yields exactly one question on its slot, and a pass that binds several entries under an unsettled pick is asked too. Evidence: scratch-mirror/targeted-2026-10-28/results-3.md, cases V7 and V6.
