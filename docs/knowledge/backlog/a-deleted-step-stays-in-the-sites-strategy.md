---
type: Backlog
title: A deleted step stays in the site's strategy
description: After a canvas delete the canvas holds 3 steps while the WDK strategy holds 5, because a concurrent read of the strategy on WDK saved the old tree back over the save's step-tree write; WDK's strategy GET is a read-modify-write.
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

**Why it happens.** A read of a strategy on WDK is also a write, and nothing stops it from
running beside the save's step-tree write. `StrategyService.getStrategy` loads the
strategy, refreshes its step sizes, and saves it back to record the view time through
`StepFactory.updateStrategy`, which overwrites `root_step_id` and re-saves every step the
loaded copy holds, with no version check. The gene-set refresh the flip save deferred
(`jobs`, `strategy:refresh_gene_set[1192]`) read the strategy in
`veupathdb_mcp/wdk/gene_set_steps.py::_count_strategy_steps` from 04:41:34.83 to
04:41:35.93. The delete save's `PUT .../step-tree` ran from 04:41:34.69 to 04:41:35.79.
The read loaded the 5-step tree before the write committed and saved it after, so WDK
holds the old root and the dropped steps belong to the strategy again. The save's own
read-back (`services/strategies/sync.py::_detached`) only checks that every pushed step is
in the strategy, so a strategy that holds more than the push, under another root, passes.
The refresh job takes no thread lock, so nothing orders its reads after the save.

**Fix.**

- veupathdb-py: `update_strategy` already reads the strategy back after the write. It
  compares the read tree with the tree it sent and sends it again when WDK holds another,
  a bounded number of times, then raises. A reader PathFinder does not control (the
  researcher's own browser on the site) can revert the write the same way. A WDK rule
  records that a strategy read writes the strategy.
- PathFinder: the gene-set refresh reads the strategy under the thread's strategy write
  lock (`services/strategies/write_lock.py`), so its reads never overlap a save.

**What you'd get.** The delete save's read-back finds root 227283440 over 227283340 and
227283350, the orphan deletes of 227283370 and 227283450 succeed, and the next turn reads
3 steps.
