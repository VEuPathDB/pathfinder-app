---
type: Decision
title: A built turn is asked to verify once
description: An output validator on the Lead refuses the first answer of a turn that built steps and neither dispatched nor passed verification, and it fires at most once per turn so a second answer stating why a check is impossible still reaches the user. Instruction prose and a hard block that ends the turn were both rejected.
tags: [agents, lead, verification, ergonomics]
generated: { by: claude-code/opus-5, at: 2026-09-01T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-01T00:00:00Z }
status: stable
---

# What was decided

The precondition gate decides which tools the Lead can reach. It offered
`verify_strategy` at the right step of a live heat-shock export and the Lead
answered anyway, closing with "I'm stopping here rather than report a gene
count" after `create_eda_step` had succeeded. A gate hides a tool; it cannot
compel a call.

**The refusal is a `ModelRetry` on the Lead's answer.** It reads this turn's
`TurnMarkers`: when the turn built something and verification neither ran nor
succeeded (`TurnMarkers.build_unverified`), the first `final_result` is refused
with the step ids it built and the two moves that answer the refusal - call
`verify_strategy`, or say in the reply why a check is not possible right now.
The rule lives in the Lead's turn contract as the unverified-build rule
(`ai/lead/turn_contract.py`, `decisions/one-turn-contract.md`).

**It fires at most once per turn**, tracked as `contract_refused` on the same
markers, which every rule of the contract shares. The second answer goes
through even when it still declines: only the model knows whether a check is
possible on this turn, so the contract compels the attempt and not the outcome.
A verification that ran and reported failure is not asked again either, which
is why `verification_dispatched` is a marker of its own: `verified` follows the
digest's verdict, and a failed check is still a check.

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
