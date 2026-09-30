---
type: Backlog
title: A case compares the records two turns showed
description: The eval corpus scores each turn's text, so a case cannot state that a later turn shows the same sampled records an earlier turn showed; an expectation field and the runner's per-turn record ids would let uat-dry3-d-hostdb hold the same-sample rule.
tags: [evals, devtools, facts]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A case compares the records two turns showed

**What I did.** Wrote `uat-dry3-d-hostdb`: turn 3 asks for a sample of five genes and
turn 4 for "that same sample of five genes again".

**What I got.** The sample's genes depend on the WDK step id of the run, so no case can
name them, and `ExpectedOutcome` has no field that compares two turns.

**Why that's wrong.** The rule the case exists for (the same sample request answers the
same genes) is held by unit tests only, not by the corpus run.

**Why it happens.** `devtools/eval_runner.run_case` keeps the last facts part only, and
`ObservedOutcome` holds each turn's text, not its record ids.

**Fix.** The runner keeps each turn's facts record ids (sources and listings) as
`ObservedOutcome.turn_record_ids`; `ExpectedOutcome.same_records_as: dict[int, int]`
scores a difference when turn N's sampled ids differ from turn M's.

**What you'd get.** `uat-dry3-d-hostdb` fails when turn 4 shows other genes than turn 3.
