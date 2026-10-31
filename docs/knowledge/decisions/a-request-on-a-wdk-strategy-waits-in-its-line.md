---
type: Decision
title: A request on a WDK strategy waits in that strategy's line
description: WDK saves a strategy back on every read, so a read that overlaps a step-tree write can restore the tree the write replaced. Every request PathFinder sends on a strategy holds a Postgres advisory lock for that strategy for as long as the request runs, and a step-tree write fails when the read that follows it does not answer the tree written. Ordering the refresh behind the thread's lock, a bounded resend, and a gate in the client library were rejected.
tags: [wdk, strategy, sync, postgres, gene-sets]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: stable
---

# What WDK does

`GET /users/{id}/strategies/{id}` is a write.
[`StrategyService.getStrategy`](https://github.com/VEuPathDB/WDK/blob/master/Service/src/main/java/org/gusdb/wdk/service/service/user/StrategyService.java)
loads the strategy, updates the stale step sizes, sets the last view time and calls
[`StepFactory.updateStrategy`](https://github.com/VEuPathDB/WDK/blob/master/Model/src/main/java/org/gusdb/wdk/model/user/StepFactory.java),
which writes `root_step_id` and every other column of the loaded copy and saves every step
the loaded copy holds. There is no version check. `PATCH` and `DELETE` on the strategy load
and save it the same way. `PUT .../step-tree` (`replaceStepTree`) writes the new root,
the new steps, and the orphaned steps without their strategy, in one transaction.

So a read that loads the strategy before a step-tree write commits, and saves it after,
puts the old root back and gives the orphaned steps their strategy again. WDK answers
both requests without an error, and a later `DELETE` of an orphaned step is a 409 because
the step belongs to the strategy again.

# What was decided

**Every strategy request holds the strategy's line.**
`services/strategies/strategy_line.py::held_strategy(site_id, wdk_strategy_id)` holds the
Postgres advisory lock `wdk-strategy:<site>:<strategy id>` on a session of the
application's pool for one request: a step-tree write with the read the client sends after
it, a name or saved-mark `PATCH`, a read, or a delete. The api and the worker install the
Postgres line at startup (`use_strategy_line(postgres_strategy_line(...))`); a process that
installs none, such as the unit tests or the chat debugger, orders its own requests with an
in-process lock per strategy. The line is a leaf: code that holds it sends one request and
takes no other lock, so it cannot deadlock with the thread's locks. The unit test
`test_every_strategy_request_waits_in_its_line` reads the source and fails on a strategy
request outside the line.

**A write the strategy does not hold is a failed push.** `sync_strategy_for_site` compares
the tree the read after the write answers with the tree it sent. A different tree raises
`TreeNotHeldError` (409), so the edit is reported like a step-tree write the site refused:
the canvas route refuses the edit and keeps the stored strategy, a build records the
failure on its root, and the tree is not recorded as the one the strategy holds, so the next
edit sends it again. Nothing resends it in a loop. With every PathFinder request in the
line, a different tree means a reader PathFinder does not control, such as the researcher's
own browser on the site.

# What was rejected

**The refresh reads under the thread's strategy write lock.** The canvas holds that lock
across its write, but a turn's writes do not, and taking it in the refresh was already
rejected because a turn sent after an edit waited about 30 s behind the gene read
([the refresh decision](the-strategy-gene-set-refreshes-in-a-job.md)). The line is held only
for the strategy read, not for the gene report.

**A bounded resend of the tree.** It hides the cause, and a reader that keeps the old tree
open answers each resend the same way.

**A gate in `veupathdb-py`.** The client already gates searches through a host-installed
gate, but neither a `PUT .../step-tree` nor the strategy id reaches it, and a client change
needs a release of `veupathdb-py` and of `veupathdb-mcp`. The control tests of
`veupathdb_mcp.controls` read the step's strategy inside the library, outside this line;
the backlog holds that item.
