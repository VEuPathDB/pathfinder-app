---
type: Decision
title: A claim that a criterion was preserved is computed from the two specs, never written by a model
description: An edit turn compares the spec it started from against the spec it produced, and what the pass did to each criterion is that comparison, never the pass's own word. The Lead's "the rest is unchanged" sentence is written from that comparison and from nothing else.
tags: [agents, strategy, frame]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# The decision

`StrategyDomainState` carries `spec_before_turn`, a deep copy of the spec as
the pre-turn hook found it, once that spec is reconciled with the live graph
(`domain/strategy/spec_reconciliation.py`): a criterion whose step the strategy
no longer holds is not one this turn can keep. It also carries
`spec_before_dispatch`, the committed spec as the running dispatch found it,
which is what a dispatch plans and restores against when one turn writes twice.
`domain/strategy/spec_diff.py::diff_specs` compares
either against the spec the pass produced and reports one `CriterionChange` per
criterion: `kept`, `changed`, `added` or `dropped`.

Two consequences follow, and both are enforced in code rather than in a prompt:

1. `FrameResult.changes` is set by the dispatch from the computed diff
   (`ai/lead/frame_dispatch.py::derived_changes`) and is omitted from FRAME's
   schema: a criterion is `kept` only when none of its wire values moved, and a
   `dropped` criterion carries the reason `drop_criterion` recorded. The pass
   writes no account, so no account can disagree with what it did; see
   [the requirement lifecycle is derived](the-requirement-lifecycle-is-derived.md).
2. The ledger's `FrameSection` exposes the diff as a computed field, derived
   from the same two specs. The Lead's instructions say a preservation claim is
   written from `ledger.frame.diff` and from nothing else.

`spec_before_turn` is deep-copied twice on purpose: once by the pre-turn hook,
and once again where `AgentToolState.operational_spec_draft` is seeded, so a
sub-agent's tools cannot mutate the record of what the turn started with.

# The alternative that was rejected

**Tell the model to preserve the rest, and trust the reply.** That is what the
product did. A measured run asked to change one filter and keep the rest, came
back with two of three criteria, and said the rest was preserved; a second run
narrowed a "kept" organism from the genus to one strain, because a kept
criterion was re-bound from its own 60-character label and every unstated
parameter was re-derived from that sentence. A prompt cannot make a claim true
after the fact, and nothing existed that could tell the claim was false.

**Have the model emit the diff and use it as the diff.** Rejected for the same
reason: the account and the state would then be the same object, and a wrong
account would be self-certifying.

**Have the model emit the diff and refuse the pass when it disagrees.** The
product did this: a criterion declared `kept` whose values moved, or one gone
from the spec without a declared drop, was a retry. The refusal checked the
model's label, not the values, so a pass that moved exactly what the request
asked was refused for a wrong word, and the retry spent a budget on the label.

# What it costs

The Lead reads a `changed` criterion the request did not name as a change the
turn made, and reports it as one; nothing refuses it before the push. The diff is
the only account, so the reply and the facts cannot claim the criterion was kept.

The entry spec is kept out of the ledger's wire payload (`Field(exclude=True)`),
so the diff reaches the frontend without a second whole spec on every chunk.
