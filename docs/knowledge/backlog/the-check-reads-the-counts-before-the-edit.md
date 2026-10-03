---
type: Backlog
title: The check reads the counts before the edit
description: VERIFY judges a before-and-after ask against the current strategy only, fails a correct edit and makes the reply deny a count the facts show.
tags: [verification, edits]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# The check reads the counts before the edit

**What I did.** On piroplasmadb, with signal peptide (501) INTERSECT schizont expression at the 80th percentile (823, result 66), asked to raise the minimum percentile to 90 and to state the counts before and after.

**What I got.** Facts: "37 genes, 66 genes before this turn's edit" and "410 genes, 823 genes before this turn's edit". The first `final_result` was refused with the verdict "the prior 80-percentile count is unavailable for the requested comparison"; the reply then said "the prior size is not established". Diagnosis: `ungroundable_constraint` "minimum schizont expression percentile: the requested share and direction could not be read".

**Why that's wrong.** Two numbers were asked, one is given, and the other is denied beside a facts part that shows it; a correct edit is marked a failed check.

**Why it happens.** `VerificationScope` carries no pre-edit counts, so the check reads the ask against the live strategy.

**Fix.** The scope carries the turn's `before` counts (the same values `[before:]` and `[root_before]` render), and a before-and-after ask is met when both are held.

**What you'd get.** "Raising the minimum percentile to 90 took the schizont search from 823 to 410 genes and the result from 66 to 37 genes."
