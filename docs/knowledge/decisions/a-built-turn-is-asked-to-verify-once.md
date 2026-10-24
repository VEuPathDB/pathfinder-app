---
type: Decision
title: A built turn is asked to verify once
description: An output validator on the Lead refuses the first answer of a turn that built steps and neither dispatched nor passed verification, and it fires at most once per turn so a second answer stating why a check is impossible still reaches the user. Instruction prose and a hard block that ends the turn were both rejected.
tags: [agents, lead, verification, ergonomics]
generated: { by: claude-code/opus-5, at: 2026-09-01T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-22T00:00:00Z }
status: stable
---

# What was decided

The precondition gate decides which tools the Lead can reach. It offered
`verify_strategy` at the right step of a live heat-shock export and the Lead
answered anyway, closing with "I'm stopping here rather than report a gene
count" after `create_eda_step` had succeeded. A gate hides a tool; it cannot
compel a call.

**The refusal is a `ModelRetry` on the Lead's answer.** It reads this turn's
`TurnMarkers`: when the turn built something and no check of this turn returned
its review (`TurnMarkers.build_unverified`), the first `final_result` is refused
with the step ids it built and the moves that answer the refusal. A check that
was dispatched and stopped verified nothing, so it leaves the build unverified;
its stop is the recorded attempt that lets a reason stand, and the stop's summary
asks for that reason. A check parked on a call the worker or the user answers has
neither stopped nor finished, so while the dispatch is parked
(`LeadDeps.build_unverified` reads the parked dispatch the deferral recorded) the
status is not shown; the task row shows the check running.

**A reason stands only beside a recorded attempt.** `LeadResponse.unverified_reason`
holds why the check could not finish. The contract accepts it only when the turn
record shows that the check itself could not finish: a stop of the verification
pass recorded this turn (`last_phase_stop`, any reason, a budget stop among them)
or a refused `verify_strategy` call (`TurnRecord.check_could_not_finish`). A stop
of the framing or the build pass is no attempt at the check. Such an answer is not refused, even on the
first answer, and is not marked as unchecked. Without that record the refusal asks
for `verify_strategy` and says the reason is accepted only after a check stopped or
was refused, so the Lead cannot decline a check it never tried.

**The status is the system's, never read from prose.** The turn's facts show
"Nothing verified the change this turn made to the strategy."
(`TurnFacts.unverified`, from `TurnMarkers.build_unverified`) on every turn whose
build no check saw, whatever the reply says. A card carries only its reply, so the
rule neither refuses a card's reply nor marks it. No rule reads the word
"verified" in a reply: a reply that wrongly claims a check stands beside the
system's own statement that nothing checked the build, and a true sentence such as
"the step still needs to be verified" or a product named "Verified ORF" is never
refused.
The rule lives in the Lead's turn contract as the unverified-build rule
(`ai/lead/turn_contract.py`, `decisions/one-turn-contract.md`).

**It fires at most once per turn**: each rule of the contract is asked once
per turn, its kind kept on `TurnMarkers.refused_rules`, and `contract_refused`
says a rule refused an answer of this turn. The second answer goes
through even when it carries no accepted reason, marked as unchecked: only the model knows whether a check is
possible on this turn, so the contract compels the attempt and not the outcome.
A verification that returned a review that failed is not asked again either:
`verified` follows the digest's verdict, a failed check is still a check, and the
build counts as checked once `verification_dispatched` holds and
`verification_stopped` does not.

# What was rejected

**Instruction prose.** "Always verify what you build" is what the Lead's
instructions already say, in the operating loop, and the live turn had those
instructions in front of it. Adding a stronger sentence buys nothing that the
first one did not.

**A hard block: end the turn, or refuse every answer until verification
runs.** Verification can be genuinely impossible - the site is down, the step
is a draft the site never took - and a turn that cannot answer is worse for the
researcher than an answer that states the gap. The retry text asks for the
reason precisely so the second answer can carry it.

**Deriving the condition from the ledger instead of the markers.** The ledger
describes the thread's last build, which can predate this turn. The markers
belong to the message the turn answers and rotate with it, so a build from an
earlier message cannot arm or disarm the refusal.
