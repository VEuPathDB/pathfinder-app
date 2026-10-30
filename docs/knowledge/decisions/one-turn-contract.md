---
type: Decision
title: One turn contract, not seven validators
description: The Lead's seven output validators became one typed contract - a TurnRecord built from the turn's markers, a pure reconcile that returns every mismatch, and one output validator that raises one ModelRetry carrying them all, latched once per turn. Keeping a validator per failure class, matching prose for the verbs, and a UI-only marker were rejected.
tags: [agents, lead, honesty, validators]
generated: { by: claude-code/opus-5, at: 2026-09-15T00:00:00Z }
status: stable
---

> Since 2026-10-27 the rules `blamed_the_site`, `claimed_frame`, `unrecorded_question`, `unfinished_work`, `unmade_change`, `unbacked_absence` and `unstated_reading` are removed ([a refusal rests on typed state](a-refusal-rests-on-typed-state.md)). Since 2026-10-30 `misreported_change` (with `LeadResponse.strategy_changed`), `stopped_check`, `failed_check`, `unnamed_record_organism`, `unplaced_breakdown` and `unrendered_prose` are removed too: the facts part states each fact they asked the prose to state, and the note beside it is held by `note_facts` ([the product renders the facts](the-product-renders-the-facts-the-reply-narrates.md)). What follows describes the table as it was built.

# What was decided

`ai/lead/turn_contract.py` owns the Lead's reply and the check on it, and
`ai/lead/turn_record.py` owns the record the check reads:

- `LeadResponse` - the typed reply. It carries one field the runtime reads as a claim:
  `asked_questions`.
- `TurnRecord` - a frozen model of what the turn did, built by `turn_record(ctx)` from
  `TurnMarkers`, the domain state and the derived ledger.
- `reconcile(report, record) -> list[Mismatch]` - one pure function, one rule per failure
  class, in a fixed order. Each `Mismatch` carries its `kind` and the sentence the existing
  message function in `dispatch_messages.py` renders.
- `hold_the_turn_contract` - the single output validator on the Lead agent. It reconciles
  once per turn, latched on `TurnMarkers.contract_refused`, and raises one `ModelRetry`
  listing every mismatch under one heading.

Seven rules covered what seven validators covered: an unverified build, a misreported change in
either direction, an unbuilt EDA-backed criterion, prose that blames VEuPathDB for an internal
stop, a question the reply asks and does not record, an analysis reported without the set it
ran on, and an out-of-scope reply that answers anyway.

Rules added since are rows in the same table. `claimed_frame` is the misreported-change rule's
sibling for the plan: a reply whose prose says the turn framed a criterion, or added one to the
plan, is refused when `ledger.frame.diff` reports nothing added and nothing changed. The diff is
the record and the prose is the claim. This one read the prose because the plan had no typed
flag, so a small regex family matches the act ("framed",
"planned", "added ... criterion", "added ... to the plan") over the reply's undenied clauses,
and the diff guard is what keeps a reply that merely describes the plan from tripping it. A turn
whose spec started empty has no diff to read and is not checked.

Its upstream half is a dispatch refusal, not a contract rule: `run_frame` refuses a `needs_user`
pass once when its questions reach no criterion - the draft is exactly what the dispatch found,
or no criterion of it holds an open slot - and tells FRAME to record the criterion with
`set_criterion` (the values it has, null for each value the user must decide) before it asks.
The two answer one failure from opposite ends: the pass that asks about nothing, and the reply
that reports what the pass never wrote.

A standing failed check is a notice of the facts part (`TurnFacts.failed_check`), and an
audit turn shows none: an audit turn reaches no building tool and answers about the audit, not
the strategy. A digest whose strategy the site no longer holds is dropped by
`pre_turn.forget_the_verdict_of_a_dropped_strategy`: the read of the strategy answers 404 and a
listing of the user's strategies succeeds without it. A 404 alone is no proof, because a site
that is redeploying answers 404 too.

An audit run's state has no prose rule. The facts part shows each audit read of the turn
(`TurnFacts.reads`), and a plan that cannot start is refused to the Lead with its reason, so no
card and no run follow from it.

`note_facts` is the rule for what the prose may hold, and the only check on its content. The
prose is a note beside the facts part: it writes no number and no link of the turn, and names a
record only as `[record:<id>]` (`domain/reply_note.py`). It is refused on every answer up to
[the refusal bound](an-output-check-refuses-at-most-twice-and-never-on-the-last-answer.md), a
card's reply included, and takes no part in the one latch below. See
[the product renders the facts](the-product-renders-the-facts-the-reply-narrates.md).

The one latch is also what the precondition gate reads: `intent_gate.verification_pending` is
`contract_refused and built and not verified`, the condition the deleted `verification_nudged`
carried, so a turn corrected before a check passed reaches `verify_strategy` and no other tool
that writes.

`unrecorded_question` reads where the reply ends. A reply whose prose ends with a question (the
last non-empty paragraph ends with `?`, closing emphasis, code, bracket and quote marks read
through) is refused whatever the turn did and whatever `next_state` says, unless it records
`asked_questions` or the researcher answered a card under this message: a consult, or a proposal
card they accepted. The correction names the three ways out: an offer goes on a proposal card
(`propose_changes`), a question for a value goes in `asked_questions`, anything else ends without
a question. A reply that ends on a card is reconciled too, before the card is shown, by the
deferred-call handler that denies the card with the correction. A value a frame pass of the
turn leaves open is asked on the question card: `open_value_in_prose` refuses a reply that does
not end on a card while one is open, with its options from the ledger's `OPEN` line or the
question's `options`. See
[an-offer-is-a-card-not-prose](an-offer-is-a-card-not-prose.md).

`unclassified_turn` reads the classification gate: a reply on a turn whose message holds no
accepted classification, while the gate's last refusal stands, is refused with that refusal's
sentence. A card answer, a typed acceptance and a turn that re-enters a parked call are exempt.
`unsaved_controls` reads `UserIntent.named_controls`: a turn whose message names controls either
saved a control set, recorded a question, or ended on a card. A verification pass that
stopped is a notice of the facts part (`TurnFacts.stopped_check`), whether or not the turn
built; a stopped check records no verdict, so nothing else on the turn claims one.
`unmade_change` reads the values an accepted `edit_strategy` classification withdraws or states:
a turn that changed nothing, ended on no card, recorded no question and carries no refusal is
refused, unless the reply names each value in a clause that takes the change back and says why.
The correction names `delete_step` for a bare withdrawal; a withdrawal with the values that
replace it is a replacement (`contract_messages.unmade_change_message`), made through
`edit_strategy` or, for an analysis export's cut, through `create_eda_step(replace_step_id=...)`
on an export of the open analysis (`services/eda/export.open_analysis_exports`), as is a
stated value.

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
- **A typed "framed" flag on `LeadResponse` instead of the regex family.** A flag states that the
  turn framed something; it does not state which criterion, so it cannot be checked against the
  diff that names them. The diff already holds the fact, and the only thing missing was whether
  the prose claims it.
- **Matching the prose for the gene set's name.** The old substituted-analysis rule scanned the
  reply for the set's id or its name. A reply that names the set in passing passed the check
  without reporting under it, and a reply that reports correctly but paraphrases the name
  failed. A typed field is the claim, and prose is not.
- **Instructing the plain sentence and not checking it.** The instruction is there, and a turn
  under pressure still reaches for the tool name it just read in a refusal. The three shapes are
  mechanical, so the check is mechanical.
- **A UI-only marker instead of a refusal.** A card saying "this reply does not match the turn"
  leaves the wrong sentence in the transcript; the correction removes it before the user reads
  it.
- **Reconciling on every answer.** The latch is what lets a second answer through: a model that
  states why a check is impossible, or why it can say no more, must be able to reach the user.
