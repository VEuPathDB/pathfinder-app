---
type: Decision
title: A strategy has a revision history, and fork, revert and Stop read it
description: Every write of conversation_strategies appends a strategy_revisions row through one repository seam; fork and revert push the snapshot in force at a chosen message to WDK as a strategy of the thread's own, and a stopped turn restores its pre-turn snapshot as recorded. Copying the latest AST, reconstructing from the event log, a composite message key and a syncedness marker were rejected.
tags: [persistence, strategy-revision, branching, revert, cancellation, wdk]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# What was decided

`conversation_strategies` held one row per thread and nothing else. Every
operation that moves a thread backwards or sideways therefore had only the
latest AST to read: a branch taken at the turn-2 answer opened on the turn-4
tree, a revert past a build left the strategy the deleted turn had written,
and a Stop mid-build left the half-written plan on disk.

**The strategy is an append log.** `strategy_revisions` holds one row per
persisted state of a thread's strategy: the conversation, the
`strategy_revision` fingerprint, the full AST (which carries the per-step WDK
ids and counts), the record type, the step count, the WDK strategy id, the
strategy name, the message that turn ended with when it is known, and the
write time. `ConversationRepository._write_strategy` and `clear_strategy` are
the one seam that appends, so a strategy state that reaches the database
reaches the history. A write that repeats the newest row's fingerprint, WDK
strategy id and step count appends nothing.

**A message resolves to the state in force when it was written.** A snapshot
the message names wins; otherwise the newest snapshot written no later than
the message. The two rules agree in practice, because a user message row
predates the turn's strategy writes and an assistant message row postdates
them. `finalize_turn` names the turn's newest snapshot with the assistant
message it just wrote, so the exact rule is available where it matters most.

**Fork materializes; it no longer duplicates.** A fork resolves the anchor's
snapshot and pushes that tree to WDK as a strategy of its own through the
existing push path (`plan_step_pushes` with no known step ids, then
`push_steps_with_plan`, then `sync_strategy_for_site`). WDK's
`sourceStrategySignature` duplication was removed with the code that used it:
it copies a strategy as it stands now, which is the very state a branch point
must not inherit. **Every snapshot that holds a tree is pushed**, whatever WDK
id the snapshot row carries: a snapshot's own id says nothing about whether its
tree was ever pushed, because a fork's copied history carries none, so a branch
of a branch would otherwise open on a plan alone. A snapshot that holds no tree
is adopted as a plan, and a WDK refusal leaves the branch holding the plan, as
the duplication failure did before.

**A branch is refused rather than approximated.** A thread that holds a
strategy and no history at all predates this store, so its branch point cannot
be reproduced: the fork is refused with `FORK_REFUSED` (409) and the reason
the client shows. A thread whose snapshots all postdate the anchor had built
nothing yet, so the branch opens with no strategy. A branch is also refused
while a durable task is running in the copied prefix: the worker resumes a
parked call on the thread that deferred it, so a copy of that checkpoint would
stay mid-turn for good.

**Revert materializes too; a stopped turn rolls back.** Revert reads the
snapshot in force at the target before the cut, deletes the snapshots at or
after it, and adopts that snapshot through the same
`materialize_strategy_snapshot` a fork uses: the tree is pushed again and the
thread holds a WDK strategy id and step ids of its own. The steps a snapshot
names may have been edited by the very turns the revert deletes, and a branch's
copied snapshots name none at all, so a restore that wrote the snapshot back
verbatim left a branch holding a plan with no counts and no result. The route
therefore carries `require_registered_wdk_identity`, exactly as the fork route
does: a revert that pushes is a WDK write. A refusal from WDK leaves the thread
holding the plan, as a fork's does. When no snapshot precedes the target and
the thread does have a history, the strategy is cleared: it did not exist yet.
A stopped turn reads the newest snapshot id as the turn opens and, on cancel,
deletes what the turn appended and restores that snapshot, or clears the
strategy when the turn opened with none. The turn's epilogue then emits
`data-strategy-revision` for the restored state directly after
`data-turn-stopped`, so the client's superseded logic and the panel agree with
the transcript.

**A restored snapshot loses the readings it cannot vouch for.** Step counts,
step validations and push errors were measured against a tree that has moved
since, so they are dropped. A stopped turn keeps the WDK step ids, because it
is undoing writes made against those same steps and nothing has moved under
them. A fork and a revert drop them: both push the tree again and take the ids
WDK answers with, and a fork's copied history carries none to begin with,
because a branch never owned its source's WDK strategy.

**A fork keeps one id space.** Copied chunks are rewritten through the same id
map the new `messages` rows are minted from, covering the `start` chunk's
`messageId`, a `user-message` chunk's `message.id` and the `turn_id` column; a
chunk id with no message row of its own is minted into the map too, so no
parent id survives anywhere in the branch. Copied log rows carry
`task_id = NULL`, because that column is a cascading foreign key to the
parent's `background_tasks`. The fork's conversation row copies
`assistant_id` and `application_id` from its source.

**A copy keeps its source's time, and the anchor cuts the notes too.** Revert
cuts messages, notes and snapshots on `created_at` and log rows on
`emitted_at`, so every copied row is stamped with its source's time rather than
the moment of the branch. A copy stamped at branch time is newer than every
message it belongs to, so the first revert inside the branch deletes it and the
branch keeps its messages while losing the chunks that render them. Scratchpad
notes are copied under the same anchor cutoff as the log: a note a later turn
wrote is a later turn's artifact.

**A branch owns its gene set.** A gene set taken from
a strategy is re-synced against whatever strategy its thread holds, so a branch
that inherited `gene_set_id` would rewrite its source's saved set on its first
build. The branch starts unlinked and imports one of its own.

# What was rejected

**Copy the latest AST** (the behavior that was there). It is free and it is
wrong at every branch point that is not the last message; three filed defects
measured it.

**Reconstruct the strategy by replaying the event log.** The log has the
chunks a turn emitted, not the AST a turn persisted, so the reconstruction
would be a second, weaker writer of the same truth and would drift from the
first the moment a tool writes without emitting.

**Widen `messages` to a composite `(conversation_id, id)` primary key** so a
fork could keep its source's message ids. It fixes the id space by making one
id name two messages, which PROTOCOL 1 forbids, and it changes the key of a
runtime-owned table for a product operation. An id map costs one dict.

**A syncedness marker on `strategy_revisions`** that survives the copy, so a
revert could tell a snapshot whose tree is live on WDK from one whose is not
and write the first back verbatim. It is a migration plus a claim a snapshot
cannot make honestly: a marker written at push time says nothing about whether
a later turn edited those steps. Pushing every tree needs no column and gives
one answer everywhere.

**A `strategyRestored` field on `data-turn-stopped`.** The chunk belongs to
`assistant_core`, which may not name a strategy, and no client reads such a
field; the restored state is already reported by the `data-strategy-revision`
chunk the epilogue emits directly after it.

# What would falsify this

`apps/api/src/pathfinder/tests/integration/persistence/test_strategy_revision_store.py`
fails if a strategy write stops appending, or if a message stops resolving to
the state in force when it was written.
`.../test_fork_materializes_revision.py` fails if a branch takes the latest
tree, keeps a parent message id, keeps a parent `task_id`, loses the
assistant id, or stops refusing a thread with no history.
`.../test_revert_restores_revision.py` and
`.../integration/conversation/test_stop_restores_strategy.py` fail if a revert
or a Stop leaves the strategy where the deleted turns put it, and the first
also fails if a revert stops pushing the tree it restores.
`.../integration/http/test_revert_route.py` and
`.../unit/transport/test_wdk_gate_route_table.py` fail if the revert route
stops requiring a registered login.
`.../unit/services/strategies/test_materialize_snapshot.py` fails if a
materialized snapshot reaches WDK carrying its source's step ids.
The full case matrix, one invariant per sentence, is
[thread surgery invariants](../conventions/thread-surgery-invariants.md).
