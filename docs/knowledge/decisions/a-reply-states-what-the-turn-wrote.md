---
type: Decision
title: A reply states what the turn wrote
description: The Lead's answer carries a required strategy_changed flag, and an output validator refuses once, in either direction, an answer whose flag disagrees with the turn's write markers. Matching the prose for change verbs and a UI-only "strategy unchanged" card were rejected.
tags: [agents, lead, honesty, validators]
generated: { by: claude-code/opus-5, at: 2026-09-14T00:00:00Z }
verified: { by: claude-code/fable-5-1, at: 2026-09-14T00:00:00Z }
status: stable
---

# What was decided

`LeadResponse` has a required boolean, `strategy_changed`. The Lead fills it on every answer.
`refuse_a_misreported_change` (`ai/lead/lead_agent.py`) reads the turn's markers
(`TurnMarkers.built`, `TurnMarkers.edited`, together `changed_strategy`) and raises one
`ModelRetry` when the flag and the markers disagree: a reply that reports a change the turn
never wrote is told the strategy is exactly as the turn found it, with its step and root
counts; a reply that hides a change the turn did write is told to report it. The refusal is
asked once per turn, so a second answer reaches the user.

Every path that writes the strategy sets a marker: a build and a resync through
`PipelineState.record_build`, a clear through `edited`. A recovery pass records a build only
when the strategy's revision hash or its pushed WDK ids moved, so a pass that repaired
nothing marks nothing.

# Why

A live turn answered "I removed that unfiltered essentiality criterion" after calling only
read tools. Nothing in the pipeline compared what the reply claimed with what the turn did,
so the user was told a change happened that did not. The typed flag turns the claim into a
value the runtime can check against the record, the same way `asked_questions` turns a
question in prose into a value the next turn reads.

# What was rejected

- **Matching the prose for change verbs.** A list of verbs ("removed", "replaced", "added")
  fits the one measured reply and misses the next phrasing, and it fires on a reply that
  describes a change the user asked for without claiming it happened.
- **A "strategy unchanged" card in the thread instead of a refusal.** It contradicts the
  false sentence visibly but leaves it in the transcript; the refusal removes it before the
  user reads it.
- **A flag with a default.** A default of false passes the validator for the exact reply that
  motivated the check: a model that believes it changed the strategy would leave the default
  in place and the claim would stand.
