---
type: Backlog
title: The retired row names the dropped criterion's requirement
description: A delete retires the requirement the deleted step answered, but the row prints the classifier's withdrawn label, which for a combination names both sides, so a live criterion reads as retired.
tags: [facts, requirements, edits]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# The retired row names the dropped criterion's requirement

**What I did.** On giardiadb, built "protein kinase domain but no transmembrane domain" (kinase 264 genes MINUS the TM step), then "remove the transmembrane domain exclusion".

**What I got.** `classify_user_intent` withdrawn `{"kind": "combination", "label": "protein kinase domain AND no transmembrane domain"}`; facts `'protein kinase domain AND no transmembrane domain' is withdrawn`, while the kinase step still runs (264).

**Why that's wrong.** The row says the kinase requirement is gone; the strategy holds it.

**Why it happens.** `ThreadRequirements.record` retires the constraint the classifier withdrew and the retired row prints that constraint's label, not the requirement text of the dropped criterion `step_196980f0`.

**Fix.** An approved delete retires what only the deleted criteria stated; the row is derived from the dropped criterion's own text, and a withdrawn combination retires the combination row alone, never a side that a live step answers.

**What you'd get.** `'no transmembrane domain' is withdrawn`.
