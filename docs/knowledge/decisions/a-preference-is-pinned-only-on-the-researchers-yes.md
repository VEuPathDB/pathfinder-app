---
type: Decision
title: A preference is pinned only on the researcher's yes
description: Only the Lead holds remember, and a preference it would store waits on a card the researcher approves; FRAME, EXECUTION and VERIFY store no memory with it. Taking the tool from the sub-agents alone, and screening every in-process read, were rejected.
tags: [memory, lead, security, approvals]
generated: { by: claude-code/opus-5, at: 2026-10-11T00:00:00Z }
status: stable
---

# What was decided

`remember` is a Lead tool only (`ai/lead/lead_memory_tools.py`); the FRAME, EXECUTION
and VERIFY toolsets do not hold it. A call with `kind="preference"` raises
`ApprovalRequired` until the researcher approves it, so the turn parks on a card whose
first line is the question `ask_about_the_preferences` writes: "Remember in your later
conversations: <name>: <summary>?". The memory is stored only when the approved call
runs. Every other kind is stored at once, because no other kind is pinned.

# Why

A preference is pinned into the instructions of the Lead and every sub-agent on every
later turn, in every conversation on the site
([standing memories are pinned](standing-memories-are-pinned-and-the-rest-recalled.md)).
The sub-agents read text other people wrote: public strategy names and descriptions,
search and study descriptions, web pages and papers. A sentence in that text that
reads as an instruction could become a standing instruction with no one seeing it. The
card shows the researcher the exact words before they become one.

# What was rejected

- **Take `remember` from the sub-agents and keep no card.** The Lead reads what the
  sub-agents report, so text they relay can still reach a `remember` call.
- **Screen every in-process tool result that carries third-party text.** It costs a
  model call on each catalog read FRAME makes and still lets a missed injection write a
  standing instruction; the card closes the write itself.
