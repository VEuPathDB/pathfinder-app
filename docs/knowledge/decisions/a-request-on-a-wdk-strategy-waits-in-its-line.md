---
type: Decision
title: A request on a WDK strategy waits in that strategy's line
description: WDK saves a strategy back on every read, so a read that overlaps a step-tree write can restore the tree the write replaced. veupathdb-py passes every request on one strategy through a gate the host installs, and the api and the worker install veupathdb-mcp's Postgres line there, so one request per strategy runs at a time across the deployment; a step-tree write fails when the read that follows it does not answer the tree written. Ordering the refresh behind the thread's lock, a lock at each PathFinder call site, and a bounded resend were rejected.
tags: [wdk, strategy, sync, postgres, gene-sets]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: stable
---

# What WDK does

`GET /users/{id}/strategies/{id}` is a write. `StrategyService.getStrategy` loads the
strategy, updates the stale step sizes, sets the last view time and calls
`StepFactory.updateStrategy`, which writes `root_step_id` and every other column of the
loaded copy and saves every step the copy holds, with no version check. `PATCH` and
`DELETE` load and save it the same way
(`veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`, WDK-STRAT-008).

So a read that loads the strategy before a `PUT .../step-tree` commits, and saves it after,
puts the old root back and gives the orphaned steps their strategy again. WDK answers both
requests without an error, and a later `DELETE` of an orphaned step is a 409.

# What was decided

**Every strategy request waits in the strategy's line.** veupathdb-py's client passes every
request on `/users/{user}/strategies/{id}` and below through `strategy_gate()`, keyed by site
and strategy id. The api and the worker install
`veupathdb_mcp.strategy_line.install_strategy_line` at startup, beside the search line
(`main.py::_install_the_wdk_lines`, `jobs/worker.py`); the served tool server installs the
same line. Each request holds the Postgres advisory lock `wdk-strategy:<site>:<strategy id>`
on a connection of the line's own pool (`STRATEGY_LINE_POOL_SIZE`,
`STRATEGY_LINE_MAX_OVERFLOW`, `STRATEGY_LINE_POOL_TIMEOUT_SECONDS`, 1, 1 and none by
default), so the line never takes a connection from the request pool. One place covers
PathFinder's reads, its name and saved-mark `PATCH`es, its deletes, its step-tree writes
and every strategy read inside veupathdb-mcp, such as the control tests' copy of a step's
tree. The gene-set refresh's read is ordered behind a save's step-tree write this way,
without the thread's lock.

**A write the strategy does not hold is a failed push.** `sync_strategy_for_site` compares
the tree the client's read-back answers with the tree it sent. A different tree raises
`TreeNotHeldError` (409), so the edit is reported like a step-tree write the site refused:
the canvas route refuses the edit and keeps the stored strategy, a build records the
failure on its root, and the tree is not recorded as the one the strategy holds, so the next
edit sends it again. Nothing resends it in a loop. With every in-deployment request in the
line, a different tree means a reader outside it, such as the researcher's own browser.

# What was rejected

**The refresh reads under the thread's strategy write lock.** The canvas holds that lock
across its write, but a turn's writes do not, and taking it in the refresh was already
rejected because a turn sent after an edit waited about 30 s behind the gene read
([the refresh decision](the-strategy-gene-set-refreshes-in-a-job.md)).

**A lock at each PathFinder call site.** It needed one wrap per strategy request, about
twenty, and could not reach the requests veupathdb-mcp sends.

**A bounded resend of the tree.** It hides the cause, and a reader that keeps the old tree
open answers each resend the same way.

# What it costs

A process sends at most two strategy requests at a time with the default pool, the same
size as the search line. The line adds two connections to the api, the worker and wdk-mcp
each ([the connection budget](../conventions/database-connection-budget.md)).
