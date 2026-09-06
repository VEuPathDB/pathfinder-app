---
type: Decision
title: A dead worker fails its turn by heartbeat, at one minute of silence
description: The maintenance sweep releases the jobs of a worker whose heartbeat is older than 60 s as well as the jobs past the started-age timeout, Stop releases the same job on the spot, and a released turn closes its open tool calls first; the window is 60 s because the beat now comes from a thread of its own, measured at 0.315 s of age inside a job that held the event loop for 5 s against 5.028 s without the thread. A heartbeat task on the worker's own loop was rejected: it beat zero times in the same 5 s.
tags: [jobs, procrastinate, chat, worker, reliability, protocol]
generated: { by: claude-code/opus-5, at: 2026-08-29T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-29T00:00:00Z }
status: stable
---

# What was decided

A chat turn runs on the worker. When the kernel kills that worker, the turn's
procrastinate job stays in `doing` on a worker id that will never report again,
holding `lock=<conversation id>`, and the thread's newest chunk is whatever the
turn had written. Three rules now end that turn.

**The sweep names a dead worker by its heartbeat, after one minute of
silence.** `jobs/maintenance.py::release_stalled_jobs` asks the job manager
twice: once with `seconds_since_heartbeat=worker_dead_heartbeat_seconds`
(default 60, minimum 60), which reads `procrastinate_workers.last_heartbeat`,
and once with the deprecated `nb_seconds=worker_stalled_job_timeout_seconds`
(default 3600), which reads the job's `started` event. The two sets are merged
by job id and the heartbeat reason wins. The sweep is `cron="* * * * *"`, so a
killed worker loses its turn one to two minutes after it dies, instead of an
hour later.

**Stop does not wait for the sweep, once the worker is that quiet.**
`cancel_turn` and `cancel_active_turn` write the cancel request a live worker
polls, then call `release_dead_turn(conversation_id)`, which releases the
conversation's chat-turn job through the same `release_job` the sweep uses,
and only when that job's worker has been silent past the same 60 s. A cancel
request is a row; a dead worker reads no rows, so without this the user's Stop
changed nothing on screen. A worker that died more recently than the window
still owns its turn, and Stop leaves the request for the sweep.

**A released turn closes its tool calls before its terminator.**
`assistant_core.conversation.open_tool_calls` reads the turn's own chunks and
writes one `tool-output-error` per call that carries an input and no result,
before `error`, `data-turn-failed`, `finish` and `done`. The turn runner does
the same from an in-memory tracker when its own driver raises.
`PROTOCOL.md` 1.3.1 states the rule, so a client never renders a running tool
call inside a finished turn.

**The beat comes from a thread, not from the event loop the jobs run on.**
Procrastinate creates `_update_heartbeat` as a task beside the job tasks
(`worker.py::_start_side_tasks`), so a job with one synchronous call stops the
beat for as long as it holds the loop. `jobs/heartbeat.py::HeartbeatThread`
runs the same refresh (`procrastinate_update_heartbeat_v1`) from a thread with
its own event loop and its own connection, at
`worker_heartbeat_interval_seconds` (default 5). `jobs/worker.py::amain`
builds the `procrastinate.worker.Worker` itself instead of calling
`run_worker_async`, because the thread needs the `worker_id` the worker
registers; that is the only reason.

# The two heartbeat windows, and what each one means

`procrastinate_workers.last_heartbeat` is read by two rules with different
consequences, and neither number is the other's.

| Window | Where | Meaning |
| --- | --- | --- |
| 30 s | `platform/health.py::WORKER_HEARTBEAT_MAX_AGE_SECONDS` | `/health/system` reports `workerAlive:false`. A warning about responsiveness. Nothing is failed. It matches procrastinate's own `stalled_worker_timeout`. |
| 60 s | `worker_dead_heartbeat_seconds` | The sweep and Stop fail the jobs that worker holds and release their locks. Destructive: the turn ends with an error. |

The health window stays at 30 s. Reporting "not heartbeating" early is useful;
failing a turn early is not the same act and does not get the same number.

# What it looked like without this

One prompt on plasmodb called `search_eda_studies`. The worker
(`mem_limit: 2g`) built the EDA study index cold, docker reported `oom` and
`die 137` on `pathfinder-worker-1` 49 seconds after the call, and the worker
restarted. The job stayed `status=doing` on the dead worker id, holding the
conversation lock, and the thread's newest chunk stayed
`tool-input-available`, so the card read "Running" with no end. The user's
Stop wrote a cancellation row that only a live worker reads.

# Why 60 s, and why 300 s was needed before

The window was 300 s because a live worker was measured 153 s behind: during a
VectorBase FRAME of about six minutes, with the worker actively logging WDK
calls, `procrastinate_workers.last_heartbeat` was 153 s old. At 60 s the sweep
would have written `tool-output-error`, `error`, `finish` and `done` into that
healthy turn and called `finish_job(FAILED)` on a job still executing.

The thread removes that gap, and the removal is measured twice.

| Where the beat runs | Beats in 5 s | Widest gap |
| --- | --- | --- |
| A task on the worker's event loop | 0 | 5.004 s |
| `HeartbeatThread` | 10 | 0.511 s |

That is `tests/unit/jobs/test_worker_heartbeat.py`, at a 0.5 s interval, with
one job holding the loop for 5.00 s. `tests/integration/jobs/test_worker_heartbeat_row.py`
reads the same case out of the database from inside the blocking job, against
a real procrastinate worker: the row is **0.315 s** old with the thread and
**5.028 s** old without it. The worst gap is therefore the interval plus about
11 ms, whatever the job does, so at the shipped 5 s interval 60 s is twelve
beats of margin.

Below 60 s is not available: the setting's floor is 60, and the sweep runs
once a minute, so a shorter window would not be read any sooner.

# Why not the started-age timeout alone

That is what [the 2026-08-17 entry](../log.md) chose, and its reason still
holds for a beat on the loop: the sweep was built on the job's `started` event
"and not the heartbeat, because a starved loop can self-prune a live worker's
row". It was right about the hazard, and the thread is what answers it.
What it does not cover is the case that started this work.
`worker_stalled_job_timeout_seconds` defaults to 3600 with a floor of 300, and
it measures how long a job has been running, not whether anything is running
it. After an out-of-memory kill the thread stays locked and the card stays
"Running" for an hour. Lowering that number is not a substitute either: it is
the same number for "this worker is gone" and "this turn is taking too long",
and a legitimate turn with a durable verification tool runs for many minutes
on a worker that answers. The heartbeat answers the first question and the age
timeout answers the second, which is why both run.

# Why not have the API notice the dead worker

The API could watch heartbeats itself, but it would be a second implementation
of a state procrastinate already publishes in `procrastinate_workers`, and it
would have to duplicate the write of the turn's terminator. The cancel path
calls into `jobs/maintenance.py` instead, so there is one `release_job`, one
terminator sequence and one error text.

# Only the api writes the study index

`EMBEDDING_INDEX_SYNC_ENABLED=false` on the worker and on `wdk-mcp`, beside the
`CATALOG_REFRESH_ENABLED=false` that already keeps them from rebuilding a stale
WDK catalog. A process with the flag false never calls
`veupathdb_mcp/embeddings/record_manager.py::sync_index`; it searches what the
api wrote. A study search over an index with no membership rows degrades to a
name match with guidance rather than writing, so a turn never blocks on a sync.

The reason was measured when the index was a local model writing a file, and
the numbers are kept as history. Two processes encoding one store starved each
other: a 20-text probe took 1.170 s per text while the api was encoding against
0.485 s per text alone, the api's own encode took 704.7 s contended against
372.6 s clear, and one api warm-up and one worker build left running together
made almost no progress for over an hour.

Since [embeddings are an API call and a Postgres record
manager](embeddings-are-an-api-and-a-record-manager.md) the contention is gone -
the whole study index syncs in 3.7 s and a warm sync embeds nothing - so the
flag now buys a single writer rather than throughput. The retry this guard used
to cost a turn in the minutes after a deployment is gone with it: the api's
warm-up fills the index before it binds anything a turn reaches.
