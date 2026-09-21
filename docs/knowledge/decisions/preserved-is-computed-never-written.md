---
type: Decision
title: A claim that a criterion was preserved is computed from the two specs, never written by a model
description: An edit turn compares the spec it started from against the spec it produced, and a criterion that left the spec without a declared drop is a ModelRetry. The Lead's "the rest is unchanged" sentence is written from that comparison and from nothing else.
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

1. `FrameResult` carries `changes`, the pass's own account of an edit. In
   `run_frame`, a criterion the computed diff reports `dropped` that the
   account does not declare `dropped`, and a criterion the account declares
   `kept` whose bound values moved, are both a `ModelRetry`. The exception is
   per PARAMETER, not per criterion: a parameter the baseline listed in
   `open_params` with no resolved value holds nothing to re-bind, so filling it
   is the work the user's answer asked for. Every other movement on the same
   criterion is still refused - another value moved, a value taken away
   (`removed_params`), or the criterion put on another search
   (`rebound_search`) - because an answered slot is not a licence to re-bind the
   rest of the binding while declaring it kept.
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
account would be self-certifying. The model's `changes` is only ever an input
to a check against the computed comparison.

# What it costs

An edit turn can now fail a dispatch on a well-formed spec, when the account
does not match. That is deliberate: the retry names the criterion id and its
text, so the pass has what it needs to correct itself, and a refusal the user
sees is cheaper than a strategy that lost a filter silently.

The entry spec is kept out of the ledger's wire payload (`Field(exclude=True)`),
so the diff reaches the frontend without a second whole spec on every chunk.
