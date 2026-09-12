---
type: Decision
title: Strict state, and the checkpoints flushed to allow it
description: PipelineState now forbids unknown keys, and pre-FBV checkpoints are truncated, because a permissive default is a compatibility shim for a shape nothing writes.
tags: [migrations, agents, drift]
generated: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
verified: { by: human:ahmedOmuharram, at: 2026-08-09T00:00:00Z }
status: superseded
superseded_by: a-saved-conversation-outlives-the-build-that-saved-it.md
---

# Superseded

Superseded on 2026-09-12 by [a saved conversation outlives the build that saved it](a-saved-conversation-outlives-the-build-that-saved-it.md): the loud refusal this page relies on never reaches the researcher, because the checkpoint serializer swallows it and hands the turn a half-built state.

# The reversal

The first call here was to skip the migration plan's checkpoint TRUNCATE, on two grounds: it would destroy valid conversations, and old checkpoints degrade harmlessly because Pydantic ignores unknown keys.

The first ground was wrong. PathFinder has not shipped, so there is no conversation history worth protecting, and a compatibility shim for it is exactly the pre-release legacy this project refuses to carry.

The second ground was worse than wrong, because it was the bandaid. "Old checkpoints degrade harmlessly" is a description of a **compatibility shim**: `PipelineState` left `extra` at its permissive default, so any key the model does not declare was silently dropped. That is the same disease as an `as Step` cast. It does not just tolerate the dead five-phase shape; it means the **next** field rename half-lands, with writers setting a key readers quietly ignore, and nothing failing.

# What was done instead

- `PipelineState` sets `extra="forbid"`. A stale or misspelled field is a loud `ValidationError`.
- Migration `2026_08_09_0001` truncates the LangGraph checkpoint tables so no pre-FBV checkpoint can meet the strict model. In-flight conversations resume from a fresh turn.

Strictness was verified as viable before committing to it: LangGraph injects no keys of its own (41 graph tests and 17 checkpointer round-trip tests pass under `forbid`; the only failures were the three compatibility tests written the turn before, which now assert rejection instead).

Confirmed on a live turn after the migration: FRAME to BUILD to VERIFY on plasmodb, the built strategy, 609 signal-peptide genes intersected with 1,649 transmembrane genes to give 326.

# The general rule

Before shipping, prefer the loud failure. A permissive default that lets a dead shape load is not robustness, it is a second source of truth with no owner.

# Anchor

`ConfigDict(extra="forbid")` on `TurnState` and `StrategyDomainState`, which `PipelineState` inherits and composes, plus migrations `2026_08_09_0001` and `2026_08_21_0001`. Guarded by `TestCheckpointsFromBeforeTheFbvFlip` in `tests/unit/ai/graph/test_state.py`, which asserts a pre-flip payload and a typo'd field name both raise.

Every state shape change since carries its own flush for the same reason: `2026_08_21_0001` truncates the checkpoint tables because the strategy fields moved under `domain`.
