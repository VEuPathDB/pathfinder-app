---
type: Decision
title: One commit path writes a strategy
description: Every write of a step or a tree to WDK goes through commit_tree, which reads what WDK holds, plans against it, validates once, writes each step with its settings, puts the tree and reads it back; four writers that each carried part of a step were rejected.
tags: [strategy-graph, wdk, commit]
generated: { by: claude-code/opus-5, at: 2026-11-23T00:00:00Z }
status: stable
---

# Decided

`commit_tree` in `apps/api/src/strategist/services/strategies/commit_tree.py` is the one
function that writes a step or a strategy tree to WDK. The edit path, the build, the
recovery resync, the snapshot materialize, the saved subtree, the gold strategy and the
seed measurement all call it; an import-linter contract and a unit test name the modules
that may call a WDK strategy write.

A commit runs in this order:

1. It refuses a tree the site cannot run (`what_the_site_cannot_run`, the record classes),
   before any write.
2. It reads what WDK holds for every mapped step (`reconcile_sync_state_with_wdk`): the
   strategy, and each mapped step outside the live tree on its own, a combine with its
   operator. The group name a combine holds is read from the step WDK holds. A step WDK
   no longer holds is unmapped. A read that fails stops the commit with nothing written, and the
   failure says whether the site did not answer or answered with a strategy that does not
   parse; the next commit reads again and writes the edit. A clear whose read fails
   raises, and the graph is restored. What WDK
   held is not kept between commits; every commit reads it again.
3. It makes the id-list datasets a gold strategy names and binds the steps to them.
4. It plans each step against what WDK holds (R1-R4 below), validates every step it
   writes once, writes the steps, puts the tree and reads it back (R5).

- R1. A value that moved against what WDK holds is stated; the rest is context. A value
  the earlier plan stated and this plan no longer states has moved too: the step is written
  without it and WDK takes its default. Each
  written step is validated once, and every refusal is returned together. A context value
  goes to WDK as WDK holds it, and the plan keeps the value it states: what WDK holds
  decides what is sent and is compared, and never replaces a value in the plan.
- R2. A refusal on a step WDK does not hold makes a draft; on a step WDK holds, a failure.
  Either keeps the tree from being put.
- R3. Filters ride the step write. A new step is created without its filters, the filters
  WDK added are recorded from the read after the create (`filters_wdk_added`), and the
  plan's filters follow in one search-config PUT that carries the held list with the
  plan's change.
- R4. A build passes the tree it held before as `old`. An unchanged step keeps its WDK
  step, a moved value is a PUT, a moved search a new step and new combines above it, and
  every WDK step a recreate replaced or the tree dropped is deleted after the put.
- R5. After the put the strategy is read back, and every setting other than the
  parameters that differs from the plan is a failure that names the field. Parameters are
  excluded because WDK answers its own spelling.

A saved or internal strategy is kept whole or not at all: on a refusal, a failed put or a
departure after the put, the strategy or the steps it made are deleted.

When the turn's read of what changed on the site fails, a canvas edit still commits, and
the commit's own read of what WDK holds sees a value set on the site that the plan does not
state. The plan is what the thread states, so the commit writes the plan's value over it.
This is accepted while that read fails; the turn that reads the site again takes the change.

A step that has no `filters_wdk_added` record (an imported step, or one stored before the
record existed) takes it from the first read of what WDK holds: every held filter whose name
no plan states is WDK's own. So a commit that changes nothing writes nothing, and the step and
its combines keep their WDK steps. The default of a filter the plan states is learnt from the
read after the write that drops that filter, so its removal is never confused with a WDK
default.

The step-settings field set is `search_name`, `parameters`, `operator`,
`colocation_params`, `filters`, `wdk_weight`, `expanded_strategy_id` and `expanded_name`
(`StepSettings` in `veupathdb-py: src/veupathdb/domain/strategy/`). The display name is not
a setting. WDK holds every one of them except `expanded_strategy_id`: an inserted saved
strategy's steps are copied into the strategy that holds them, so no step names the saved
one. `SITE_HELD_SETTINGS` (`domain/strategy/site_held_settings.py`) is the one list of
the settings WDK holds. The read-back check (R5), the plan's view of what WDK holds and
the site read compare only those, and keep the graph's saved-strategy id.

The site read takes all of a site's edit or none of it. When the site's tree does not
parse (`build_snapshot_from_wdk` refuses it), it takes no value, setting or shape.

Measured before the commit path, on the stateful fake: 27 of 84 matrix cells were red
(a weight, a filter, a sort, an expansion or a validation that a writer dropped), and the
canvas undo dropped a step's weight, filters, analyses and expansion. Measured after, on
the same fake: 0 of 84 red, and the undo carries all five. On the QA sites, the last
strategy of each of 10 built eval and ranking threads held every search, operator and
weight its plan shows (16 steps, 5 combines), and the weighted root was sorted by weight.

# Rejected

- **Four writers, each given the missing fields.** The 27 red cells came from exactly that
  drift: each writer carried a different subset of a step's settings.
- **A filter pass after the tree write.** It ran only when the tree moved and never removed
  a filter.
- **`commit_tree` in veupathdb-py.** It cannot read veupathdb-mcp's validator.
- **`commit_tree` in veupathdb-mcp.** The plan, its sync state and its organism rules are
  Strategist's.
- **Keeping what WDK held in the sync state between commits.** A path that did not read
  first planned against the tree before the edit, so a refused write was never sent again.
  Reading on every commit costs one strategy read and closes that.
- **Planning against the tree before the edit.** A refused PUT or POST left WDK holding the
  old value while the plan held the new one, and no later commit wrote it.
- **Comparing parameters in the read-back check.** WDK answers its own canonical spelling;
  validation covers the parameters.

# Anchor

`commit_tree` and `_Commit` in
`apps/api/src/strategist/services/strategies/commit_tree.py`;
`reconcile_sync_state_with_wdk` and `held_before_the_commit` in
`apps/api/src/strategist/services/strategies/reconcile.py`;
`plan_step_pushes` in `apps/api/src/strategist/services/strategies/step_push_planner.py`;
`what_the_site_cannot_run` in `apps/api/src/strategist/services/strategies/record_classes.py`.
