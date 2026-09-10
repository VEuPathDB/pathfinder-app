---
type: Decision
title: A durable task reports itself on the thread, coarsely, and the per-task channel is deprecated
description: The worker writes data-task-progress and data-task-completed into conversation_events, coalesced to the first update, every five-point advance and the last one. Keeping progress on a second SSE dialect forever was rejected, because the long-running half of a turn was the half that could not resume; writing every tick was rejected, because the log is replayed for the life of the thread; deleting the per-task route was rejected as a break the frontend has not been migrated off.
tags: [assistant-core, assistant-client, protocol, sse, tasks, ws-v]
generated: { by: claude-code/opus-5, at: 2026-08-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-23T00:00:00Z }
status: stable
---

`TaskProgressEmitter` and the coalescing rule are the runtime's
(`assistant-platform: docs/knowledge/conventions/durable-background-tasks.md`).
This page records the protocol decision and what it rejected.

# What was decided

A durable task's whole lifecycle is on the thread. `data-background-task-started`
was already there, inside the turn that suspends. The worker now also appends
`data-task-progress` while the tool runs and `data-task-completed` when it
reaches a terminal outcome, both through the same log and the same cursor as
every other chunk. PROTOCOL.md 1.1.0 states the sequence and the coalescing
rule; a client that reads the main stream needs no second reader.

**The coalescing rule.** An update reaches the log when it is the first for its
task, when the task has advanced five percentage points since the last one
written, or when the last one written is ten seconds old. The final update
before the task ends is always written. The comparison is in whole percentage
points, so a rule stated as "five points" is not decided by binary floating
point: `0.15 - 0.10` is `0.049999999999999996`, and a fraction comparison would
have skipped exactly the tick the rule names.

**The chunk carries the task id as its `id`**, so section 5.2's reconciliation
collapses a task's progress into one part however many chunks were written. The
cost of an extra chunk is log bytes, not a duplicated card.

**A task that fans out suffixes that `id` with a lane.** A sweep derives one
scoped emitter per variant, and every scoped emitter carries a lane
(`<task id>:<variant id>`) and a coalescing budget of its own, so five variants
leave five parts that each advance on their own instead of one part the
variants overwrite in turn. The lane is also in the payload's `toolSpecific`,
which is where a client reads it; the `id` is a reconciliation key and nothing
parses it. A task that runs one sequence is unchanged: bare task id, one part.
The alternative was to keep one `id` and let the client fan the lanes out of
`toolSpecific` itself. It was rejected because the log would still hold one
part: reconciliation happens at reduction, so every lane but the last would be
dropped before any client saw it, and the card could not survive a reload.

**The per-task route keeps working, byte for byte.** It is deprecated, its
dialect is written down in PROTOCOL.md section 13, and one integration test
pins its exact frames against that section.

# Why

The backlog item this closes measured the cost: the thread frames
`id: <cursor>` with the chunk as the payload, and the task endpoint frames
`event: stream` with the chunk wrapped in `{type: "custom", kind}` and no
cursor. Section 3 defines two frame shapes and tells a client to reject a
third, so a conforming reader refused the task stream by construction. Every
consumer paid for two readers, two reconnect stories and two sets of types, and
got resume for neither half of the long-running one.

# What was rejected

**Leaving progress on its own stream forever.** Rejected: it is the shape the
backlog item is about. A twenty-minute enrichment is exactly the case where a
page gets reloaded, and it was the case with no cursor.

**Writing every tick to the log.** Rejected with a number: the parameter sweep
runs about fifteen minutes and its emitter flushes at up to 1 Hz, so an
uncoalesced task would leave on the order of 900 rows in `conversation_events`,
replayed on every snapshot of that thread for as long as it exists. The rule
above bounds each lane to at most twenty rows from the advance clause plus one
per ten seconds, and the reconciling `id` keeps the reduced message at one part
per lane either way.

**Coalescing on time alone.** Rejected: a task that finishes in four seconds
would report nothing but its last state, and a task that stalls would report a
tick a second while standing still.

**Coalescing on advance alone.** Rejected: a fan-out that sits at forty percent
for eight minutes while its message changes would look frozen to a reader who
reconnects.

**Tagging the rows with `task_id`.** The column exists and is the obvious hook.
Rejected: `event_stream._fetch_after` excludes task-tagged rows from the chat
stream by construction, and that exclusion is precisely what put the progress
on a second channel in the first place. The rows are untagged, so the chat
stream carries them.

**Giving the rows the suspended turn's `turn_id`.** Rejected: the stop path
reads the newest row of a thread and asks the user to cancel `row.turn_id` when
that row is not a `done`. A progress row carrying a turn id would point Stop at
a turn that already finished. The rows carry no turn id, which is what the
column's nullability already means - the chunks belong to no turn - and Stop
behaves as it did.

**Refactoring the per-task route to share the live payload builders.**
Rejected: the route's promise is that its bytes do not change. Sharing a model
with the live path would let a change to the thread's payload alter a
deprecated channel's wire silently. The two are separate and the golden test
holds the deprecated one still.

**Deleting the per-task route.** Rejected: the route's promise is that its
bytes do not change, and a host that wants progress at the worker's rate has
no other channel. `apps/web` no longer reads it: the task card renders from
the message's own parts, and the thread's tail carries the task's progress,
its outcome and the continuation on one connection.

# Consequences

- A client built from PROTOCOL.md alone renders a durable task's card, its
  progress and its outcome, and resumes all three on the cursor rule.
- `@veupathdb/assistant-client/legacy` is deprecated. It stays for a host that
  wants progress at the worker's rate rather than the log's.
- The thread's log now holds chunks that belong to no turn. Section 6.1 says so,
  and a client must accept them.
