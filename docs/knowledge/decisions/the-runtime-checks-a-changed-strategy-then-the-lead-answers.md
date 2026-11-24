---
type: Decision
title: The runtime checks a changed strategy, then the Lead answers once
description: When the Lead answers a turn that changed the strategy and dispatched no check, the Lead node makes the verify_strategy call in its place and resumes the Lead once with the verdict. The refusal that asked for a check, and the free-text unverifiedReason it accepted, are deleted. Asking once, a hard block, a check after the reply and instruction prose were rejected.
tags: [agents, lead, verification, honesty]
generated: { by: claude-code/opus-5.5, at: 2026-11-24T00:00:00Z }
status: stable
---

# What was decided

**The runtime makes the check the answer skipped.** After the Lead's run ends on a
`LeadResponse`, the Lead node reads `ai/lead/turn_record.py::owes_a_check`: a build or
edit pass of the turn wrote steps and no check saw them (`LeadDeps.build_unverified`;
a turn that only deleted or cleared steps owes none), no check of
this turn was dispatched (`TurnMarkers.verification_dispatched`), and no criterion of a
build waits on its analysis. A reply that ends on a card is a `DeferredToolRequests`,
so it is never checked. When a check is owed, `ai/graph/_lead_runs.py::the_runtime_check`
appends a `verify_strategy` call (id `call_runtime_check_...`) to the answered run's
history and the node runs the Lead once more from it. The call's `reason` is VERIFY's work
order ("Check the strategy this turn changed."); the rule for the Lead's reply rides as
the resumed run's instructions (`resume_context`), on the node's resume and on the
completion turn's, and never in the call's arguments. pydantic-ai executes the pending
call through the Lead's own toolset, so the check streams, parks and resumes as a call
the Lead made: a check that defers parks through `ai/graph/_lead_durable.py` and the
completion turn resumes the Lead with the verdict; a check that stops on its budget
returns its `VerificationStopped`, and the facts part shows the stop. The reply the Lead
writes after the verdict is the turn's reply, and the first reply is never shown.

**Once per turn.** The resume happens once per node run. The check marks
`verification_dispatched`, so a second answer is never checked by the runtime, whether
the check passed, failed or stopped.

**No reason the model writes stands.** `LeadResponse.unverified_reason`, the
`unverified_build` rule of the turn contract, its message and its `Check` key, and the
gate that narrowed a refused turn to the check (`intent_gate.verification_pending`) are
deleted. A check that cannot finish is shown by its own stop in the facts part.

**A check that read no record says so.** `domain/site_checks.py::records_read` adds one
check to every verdict: `pass` when a record read of the checker answered, `unchecked`
with `site_unanswered` (which fails `success`) when every read it tried got no answer,
and `unchecked` with `no_check` (which does not) when it read none.

# Evidence

The refusal this replaces ("nothing verified the result") fired in 25 of 58 recorded
turns, one Lead round trip each; the before count over cedar runs holds 44 such refusals
in 109 turns that changed the strategy. In `ec-final/e2` the second answer passed with a
made-up `unverifiedReason` ("Verification was unavailable in this turn ...") while
`verify_strategy` was offered and never tried. Both refute the premise of the old rule,
that only the model knows whether a check is possible.

# What was rejected

**Asking once** (the previous decision, a built turn is asked to verify once). The second
answer passes with any reason, so the rule compels nothing.

**A hard block that ends the turn.** A check that cannot finish still ends the turn with
its stop shown; ending the turn instead leaves the researcher no reply.

**A check after the reply.** The reply would be blind to the verdict, and a check that
defers would have no turn to land in.

**Instruction prose.** The Lead's instructions already say to verify what it builds; the
recorded turns had them in front of the model.

# Measurement

Per changed turn, before (Task 0) and after (Task 12): Lead model calls, turn wall time
(`timing.json`, which the chat debugger writes for every run), and the share of changed
turns that end with a recorded verdict. The refusal count goes to zero by construction
and is not a measure.
