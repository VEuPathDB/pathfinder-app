---
type: Backlog
title: A quoted value and an initial value carry their source
description: A text term the message writes in quotes and a number equal to the parameter's published initial value both show as chosen, so the source column claims decisions the assistant did not make.
tags: [facts, bound-values, source]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A quoted value and an initial value carry their source

**What I did.** On tritrypdb, wrote 'I meant the exact phrase "GPI anchored", in quotes'. On fungidb, built `GenesByLocation` on chromosome 1 with the site's start and end.

**What I got.** `Text term (use * as wildcard): "GPI anchored" (chosen)`, while the turn's ledger row grounds `exact quoted phrase GPI anchored`. `Start at: 1 (chosen)` beside `End Location (0 = end): 0 (site default)`; WDK publishes `initialDisplayValue` "1" for the start.

**Why that's wrong.** The source column tells the researcher which values the assistant decided; both rows claim a decision for a value the researcher typed or the site supplied.

**Why it happens.** `BoundValue.sourced` judges a stated value by the value's wire form against the messages, and the quotes in the message keep the term from matching; `at_default` compares against the published initial value, and the start value's initial value is read from the sheet under the organism context, where it differs from the published one.

**Fix.** Statedness compares the value against the message with quotes and case folded; `at_default` reads the initial value from the published sheet for every parameter, and a recorded `GenesByLocation` sheet pins the start value's initial value.

**What you'd get.** `"GPI anchored" (stated)`, `Start at: 1 (site default)`.
