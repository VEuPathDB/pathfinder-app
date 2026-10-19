---
type: Backlog
title: A deleted step stays in the site's strategy
description: After a canvas delete the canvas and the stored strategy hold 3 steps while the WDK strategy still holds 5, the dropped steps cannot be deleted, and a later turn reads and reports the 5-step tree; the step-tree write the save sends is not logged, so the cause is open.
tags: [canvas, wdk, strategy, sync]
generated: { by: claude-code/opus-5.5, at: 2026-10-19T00:00:00Z }
status: proposed
---

# A deleted step stays in the site's strategy

**What I did.** On 2026-10-19, `apps/web/e2e/journey/comprehensive-strategy-lifecycle.spec.ts:39`
on PlasmoDB QA through a SOCKS tunnel: a five-step strategy (GenesByText and GenesByGoTerm
under a combine, GenesWithSignalPeptide under the root combine), a text edit, a GO term
edit, the inner combine flipped from UNION to INTERSECT, then the SignalPeptide leaf
deleted on the canvas.

**What I got.** The canvas and the stored strategy hold 3 steps (the test's own read of
the nodes passed). The delete save sent `PUT /users/{id}/strategies/214644620/step-tree`,
WDK answered without an error, and the save logged "Updated WDK strategy step tree". It
then deleted the two steps it dropped, and WDK refused both:

```
DELETE /users/1216062453/steps/227283370 -> HTTP 409: Steps that are part of strategies
cannot be deleted.  Remove the step from strategy 214644620 and try again.
DELETE /users/1216062453/steps/227283450 -> HTTP 409 (same)
```

A read of strategy 214644620 after the run answered 5 steps: root 227283450 (a combine)
over 227283440 (GenesByText 48 INTERSECT GenesByGoTerm 134) and 227283370
(GenesWithSignalPeptide 479), root size 0. The next chat turn's trace read "5 steps, 0
genes", and the test's count check failed at line 145. The run before, on 2026-10-18, made
the same WDK calls in the same order and both orphan deletes succeeded.

**Why that's wrong.** The researcher sees 3 steps and the site runs 5: a count, a result
download or a later turn reads a strategy the canvas does not show.

**Why it happens.** Not known yet. No write to the strategy follows the delete save's PUT,
so either the PUT carried the old tree (`_create_or_update_wdk_strategy` in
`services/strategies/sync.py`) or WDK did not apply it. The request body is not logged.

**The work:**

- Record the step-tree body the save sends, in a test that drives this sequence (edit,
  flip, delete the last leaf under the root combine) against recorded WDK answers, and
  compare it with the tree the canvas holds.
- If PathFinder sends the right tree, reproduce the PUT alone on PlasmoDB QA and read the
  strategy back.
- Fill in the cause, fix, and what you'd get. Strategy 214644620 on the test account
  holds the state above until then.
