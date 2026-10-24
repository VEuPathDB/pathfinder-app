---
type: Decision
title: An output check refuses at most twice and never on the last answer
description: An output type checks only shape and normalizes what is unambiguous; every judgement on a FRAME, VERIFY or Lead answer is an output check that refuses only for a change the model can make, out of one budget of two refusals per pass, and never on the last answer the run allows; past that it drops what cannot stand and records a typed gap that the Lead, VERIFY and the facts part read. Refusing until the answer is fixed, per-check bounds and judgement on the types were rejected.
tags: [agents, frame, lead, ergonomics]
generated: { by: claude-code/opus-5, at: 2026-10-22T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-22T00:00:00Z }
status: stable
---

# What was decided

**A refusal asks only for a change the model can make.** A check runs only when
its condition can be met. A requirement key is refused as unknown only while the
requirement list holds keys, and a question with readings is asked for keys only
then. A report that the site refused a search is checked against the refusals
only when the pass saw one. Each refusal names the field and the change in one
sentence.

**An output type checks only shape.** Types, required fields and enums stay on
the type. What is unambiguous is normalized there: a label, a question and a reply
are clipped to their limits, a question keeps eight options at most, and an
`AskedQuestion` with one option is a question answered in words. A report's `search` or
`site` on a problem that does not take it is dropped, and VERIFY's reason, prose,
lists, row texts, sources and memory drafts are clipped to their limits. Every
judgement is an output check: the reading problems (one reading, readings beside
options, no slot, two alike, more than three), a question that decides nothing
(`hold_the_questions_to_a_dimension`), the report checks (a refusal or a route with
no search or site named), the readings check, the every-genome check, VERIFY's
digest check (a row whose status disagrees with its answer, a source that cannot be
opened, and what no read of the turn holds) and the Lead's turn contract. A column
fit's counts are the runtime's, so the runtime checks they nest where it records
them. `tests/unit/ai/test_an_output_type_checks_only_shape.py` walks every output
type of FRAME, VERIFY and the Lead and fails on any validator that is not a
normalizer, on any functional validator in a field's metadata other than a clip
from `domain/clipped.py`, and on any length or count bound.

**A shape error past the retries is a typed stop.** A shape error cannot be
degraded, so it still spends the run's output retries. A sub-agent run that ends
on "Exceeded maximum output retries" records `PhaseStop` with reason
`output_retries`: VERIFY returns `VerificationStopped` and FRAME its stopped result,
and the Lead answers the turn. When the Lead's own run ends on it, the turn ends
on the facts part (what was built, the counts, the unverified status) and a reply
that says the written answer could not be produced; the error sentence is kept for
real errors. The library raises `UnexpectedModelBehavior` for this and for other
faults with no field that names the kind, so its message is the discriminator, read
in one place (`ai/lead/sub_agent_stops.py::spent_its_output_retries`).

**One budget per pass.** `ai/agents/refusal_bound.py::may_refuse` holds
`REFUSALS_PER_CHECK = 2`, one count shared by every check of a pass
(`AgentToolState.refusals` for FRAME and VERIFY, `TurnMarkers.output_refusals`
for the Lead's rules). The Lead's prose faults hold a bound of their own
(`TurnMarkers.prose_refusals`), so rules refused first never leave a reply that
cannot render without its correction. No check refuses when the run context reports the last retry the
agent allows (`ctx.retry >= ctx.max_retries`), so the last answer always stands.

**Past the budget, a check degrades and records a typed gap.** FRAME's gaps are
`FrameResult.gaps` (`PassGap`, one kind per degrade), which the Lead reads with
the result. A report check drops the reports it refuses. A question with a reading
problem, or whose readings the site refuses down to fewer than two, reaches the
card with its text and options alone, the site's first sentence in the gap. A
question whose readings name no stated requirement keeps them, and a pick of one
carries `names_no_requirement`: its caveat and the line VERIFY and the Lead read
say the pick replaces none, so each requirement is judged on its words. A typed
reply of the Lead whose prose still writes a number, an identifier or a record's
product text outside a reference, or a reference the facts cannot render
(`turn_contract.WITHHELD_FAULTS`), is withheld: its prose becomes
`WITHHELD_REPLY`, or `WITHHELD_ALONE` on a turn with no facts, and it keeps its
questions, its state and its unverified reason, so the same prose gets the same
verdict on every answer. A reply whose only faults are a number word in a
reference's clause, a noun after a count, a link written out
(`link`), a bracket that is no reference (`malformed_reference`) or a variant's
size on its own (`standalone_count`) goes through unchecked: none of them
puts a figure the facts do not hold in front of the researcher: a link names a
page and states no number, a malformed bracket is shown as its plain words, and
a variant's size on its own is a count the facts hold, only quoted without its
count in the strategy. The facts part marks the reply unchecked. A card's reply goes through with every reference it cannot render
shown as its plain words, and the facts part carries a note that the reply holds
statements not checked against the result (`TurnFacts.unchecked`). Past the budget, or on a second answer
after the one correction, the contract still runs `reconcile` and marks any
mismatch it finds; the reply's `strategy_changed` is set to what the record holds.
A reply to a build no check saw is not a mismatch when it states the reason in
`LeadResponse.unverified_reason` beside a recorded stop or refusal of the check, or
when it is a card's reply, so the answer the refusal asks for is not marked. The
facts state that nothing verified the build; no rule reads the word in the prose
(`decisions/a-built-turn-is-asked-to-verify-once.md`).
An unheld reference reads "a count not shown", "a value not shown" or "a link not
shown", and a record by its id. VERIFY takes each unbacked item out of the review
(an unread sampled gene, a source no read returned or that carries no identifier, a
row naming a message the request lacks, an answer naming a step the strategy lacks)
and records it in `VerificationReview.withheld`, which the Lead's ledger and the
evidence card show; a met row with no answer stands unmet. An edit carries FRAME's
gaps on its `EditDelta` as a build does on its result.

# What was rejected

**Refusing until the answer is fixed.** A check whose change the model cannot
make, or will not make, then ends the turn on "Exceeded maximum output retries",
and the work the pass did is lost with it.

**A bound per check.** Six checks on one agent with three retries can still
exhaust the retries between them.

**Judgement on the output type.** A type's validator refuses every answer,
including the last, so two such problems together ended the pass on an exceeded
retry count whatever the checks' bound.
