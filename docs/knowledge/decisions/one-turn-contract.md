---
type: Decision
title: One turn contract, not seven validators
description: The Lead's seven output validators became one typed contract - a TurnRecord built from the turn's markers, a pure reconcile that returns every mismatch, and one output validator that raises one ModelRetry carrying them all, latched once per turn. Keeping a validator per failure class, matching prose for the verbs, and a UI-only marker were rejected.
tags: [agents, lead, honesty, validators]
generated: { by: claude-code/opus-5, at: 2026-09-15T00:00:00Z }
status: stable
---

# What was decided

`ai/lead/turn_contract.py` owns the Lead's reply and the check on it:

- `LeadResponse` - the typed reply. It carries three fields the runtime reads as claims:
  `strategy_changed`, `asked_questions` and `analysed_gene_set_ids`.
- `TurnRecord` - a frozen model of what the turn did, built by `turn_record(ctx)` from
  `TurnMarkers`, the domain state and the derived ledger.
- `reconcile(report, record) -> list[Mismatch]` - one pure function, one rule per failure
  class, in a fixed order. Each `Mismatch` carries its `kind` and the sentence the existing
  message function in `dispatch_messages.py` renders.
- `hold_the_turn_contract` - the single output validator on the Lead agent. It reconciles
  once per turn, latched on `TurnMarkers.contract_refused`, and raises one `ModelRetry`
  listing every mismatch under one heading.

Seven rules cover what seven validators covered: an unverified build, a misreported change in
either direction, an unbuilt EDA-backed criterion, prose that blames VEuPathDB for an internal
stop, a question the reply asks and does not record, an analysis reported without the set it
ran on, and an out-of-scope reply that answers anyway.

The one latch is also what the precondition gate reads: `intent_gate.verification_pending` is
`contract_refused and built and not verified`, the condition the deleted `verification_nudged`
carried, so a turn corrected before a check passed reaches `verify_strategy` and no other tool
that writes.

The substituted-analysis rule reads a typed field instead of the prose. The record knows which
gene set the enrichment ran on; the reply must list that id in `analysed_gene_set_ids`.

# Why

Each validator grew out of one live failure, and each carried its own latch, its own message
and its own test file. A reply that failed several was corrected one at a time, so the turn
could spend up to seven serial retries on one answer - each retry a whole model call whose
prompt carries the turn's history. A new failure class cost a new function, a new latch on
either `TurnMarkers` or `LeadDeps`, and a new place to look when a refusal fired.

One reconciliation costs at most one retry however many claims are wrong, and the model sees
every problem at once instead of discovering them one answer at a time. A new failure class is
a field on `TurnRecord` or a row in the rule table.

# What was rejected

- **Keeping a validator per failure class.** It is where the code was. The cost is the serial
  retries, and the latch-per-rule bookkeeping that made "which refusal fired" a question with
  seven answers.
- **Matching the prose for the gene set's name.** The old substituted-analysis rule scanned the
  reply for the set's id or its name. A reply that names the set in passing passed the check
  without reporting under it, and a reply that reports correctly but paraphrases the name
  failed. A typed field is the claim, and prose is not.
- **A UI-only marker instead of a refusal.** A card saying "this reply does not match the turn"
  leaves the wrong sentence in the transcript; the correction removes it before the user reads
  it.
- **Reconciling on every answer.** The latch is what lets a second answer through: a model that
  states why a check is impossible, or why it can say no more, must be able to reach the user.
