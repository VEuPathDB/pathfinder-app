---
type: Decision
title: Audits run on a queue of their own, served by a second worker in the worker process
description: An audit run is carried by procrastinate jobs on the queue "audit", which a second worker inside `python -m pathfinder.jobs.worker` serves at AUDIT_CONCURRENCY (2 by default, at most 4), so a run that takes hours never holds a slot a chat turn or a durable tool needs. One job per run is queued and one runs, under the key audit-run:<run_id>; a wait for a site is a continuation scheduled on the same queue, a job starts no unit after 30 minutes of work, and the progress lives on the run row. A model-started durable tool, the runtime's host-started tasks, a new runtime primitive and a worker container of its own were rejected.
tags: [audit, jobs, procrastinate, worker, concurrency, locks]
generated: { by: claude-code/opus-5, at: 2026-10-22T00:00:00Z }
status: stable
---

# What was decided

**A queue and a worker of their own.** `services/audit/job.py` defers the job
`audit:run` on the queue `audit`. The worker process runs two procrastinate
workers: the one that serves chat turns, durable tools and maintenance at
`WORKER_CONCURRENCY`, and one that serves only `audit` at `AUDIT_CONCURRENCY`.
A turn therefore never waits for an audit slot, and the number of runs that
read at one time has a cap. The cap is at most 4 because each running job
holds one pooled connection for its lease, and the pool of 15 stays mostly for
turns. Each worker has its own heartbeat thread; one stop signal stops both,
and when one worker ends or fails the process stops the other and exits.

**One job per run.** Every job of a run is deferred with `lock` and
`queueing_lock` both set to `audit-run:<run_id>`, so at most one job of the run
is queued and at most one is doing. A running job also holds the Postgres
advisory lease on the same key; a job that cannot take it returns before any
read. The lease is the fence for a job that the runtime's stalled-job sweep
released while its coroutine still reads. `start_run` starts nothing while a
job of the run is queued or doing, and two concurrent starts queue one job.

**A wait ends the job.** When units are left after a pass and the next pause
ends before the deadline, the job defers its continuation with `schedule_in`
on the same queue and locks, carrying the deadline and the next pause, and
returns, so no slot is held during the wait. A job starts no unit after 30
minutes of work: it continues at once in a new job at the next unit, so its
own reads keep it under the stalled-job timeout unless one unit runs long (see
the known limit). Open units are read least-tried first, so a slice that
cannot finish a pass still moves forward. No unit read starts after the
deadline, in the first pass of a continuation too; the collect stage's read of
the site's release is the one read the deadline does not stop.

**The progress is on the run.** Each stage writes `done`, `total` and its last
message into `audit_runs.stages`, which `GET /api/v1/audits/{run_id}` shows.
A wait on the deployment's search line writes "Waiting for <site>" there. No
`background_tasks` row is written for an audit.

**A run whose job is lost is queued again.** The periodic job
`maintenance:resume_stranded_audits` runs every 5 minutes
(`RESUME_STRANDED_AUDITS_CRON` in `jobs/tasks.py`) on the maintenance queue. It
defers a job for every run that is not halted, has no job queued or doing, and
is `running`, or `planned` with a deadline (a start whose job was never queued),
with the stored deadline. A run whose job is queued or doing is skipped, so the
running job's own scheduled continuation keeps its pause; the queueing lock
drops a second deferral that races the check, and the procrastinate lock and the
lease keep a second job off a run whose earlier job is still doing. Procrastinate
defers one job per scheduled time across every worker. The period is short
against the run's deadline (`AUDIT_RUN_HOURS`, 6 hours: a stranded run loses at
most about 1/72 of it) and against one 30-minute work slice, and longer than the
one-minute dead-heartbeat window in which the stalled-job sweep fails a killed
worker's job and frees the run's lock. A pass that finds the lease still held
queues a job that returns at once, and the next pass tries again. A retry
reopens the run and writes its new deadline and token in one transaction. A job
that raises stores "the audit job failed" with the error on the run and on the
unit it was reading, and erases the kept sign-in; a unit failed after its third
stop keeps that error after the stop message. The run stays halted until a new
`start_run`; the resume pass does not queue a halted run.

**The worker start reads no app table.** Only the api migrates
(`platform/migrations.py::init_db`), and the worker can start before it does. A
resume pass that runs before the audit tables exist fails as one maintenance
job, which procrastinate records, and the worker keeps serving.

**An audit shares the search line.** A genome report from an audit joins the
deployment's expensive-search line when its search was counted slow earlier in
the process ([An expensive search waits in one line across the deployment](an-expensive-search-waits-in-one-line-across-the-deployment.md)).
A turn's search on that line then waits behind at most `AUDIT_CONCURRENCY`
audit reports: a delay, not a refusal.

# What was rejected

**Resuming at worker start.** The worker read `audit_runs` before it served a
queue. A worker that starts before the api has migrated a new audit table
failed and depended on a restart, and a run stranded while that worker ran
waited for the next restart.

**A durable tool the model calls.** It takes the lock a chat turn of its
thread takes, so the next turn of the thread waits behind the job. A run takes
hours, and the thread would be unusable for all of them.

**The runtime's host-started tasks** (`start_host_task`, under a lock that is
not the thread's). The runtime defers every durable job on one queue per
process, so an audit holds one of the slots the turns and the durable tools
share, and nothing caps the number of runs reading at once. A wait for a site
needs a scheduled continuation, which `start_host_task` cannot express, so
PathFinder would keep a copy of it with one more argument. Each continuation
writes a `background_tasks` row on the thread, one for every wait, which the
Tasks panel lists and marks complete while the run is still unfinished. The
run's state is already on `audit_runs`, so a task row duplicates it.

**A new runtime primitive** (a scheduled host task on a queue the host names).
It needs a runtime release for one consumer, and procrastinate already has the
queue, the queueing lock and `schedule_in`. If a second assistant needs long
jobs, the audit job is the pattern to lift into the runtime.

**A worker container of its own.** Every deployment stage would need a new
unit, and the second container would install again every seam the worker
process installs once: the search line, the request observer, the database pool
and the heartbeat.

# Known limit

The stalled-job sweep is the runtime's and reads every queue
(`assistant-platform: docs/knowledge/conventions/durable-background-tasks.md`).
A single unit can still outlast its timeout when its request waits on the
search line, which has no bound. The sweep then releases the job; the lease
keeps a second job off the run until the first one ends.

# Anchor

`apps/api/src/pathfinder/services/audit/job.py`,
`apps/api/src/pathfinder/services/audit/units.py`,
`apps/api/src/pathfinder/jobs/worker.py`,
`apps/api/src/pathfinder/jobs/tasks.py`,
`apps/api/src/pathfinder/tests/integration/jobs/test_audit_run_job.py`,
`apps/api/src/pathfinder/tests/integration/jobs/test_stranded_audits_resume_on_a_schedule.py`,
`apps/api/src/pathfinder/tests/unit/jobs/test_audit_worker.py`.
