---
type: Decision
title: A finished job leaves no request behind, in the queue or in the log
description: The worker deletes every procrastinate job when it reaches a final state, a stalled job the sweep releases is deleted too, a data migration deleted the rows kept before, and a filter on every procrastinate log record keeps the job's name, id, queue and status and drops its arguments and result. Keeping finished rows for inspection and a regex scrub of the token alone were rejected.
tags: [jobs, privacy, logging, procrastinate, persistence]
generated: { by: claude-code/opus-5, at: 2026-10-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-09T00:00:00Z }
status: stable
---

# What was decided

**A job is deleted at its final state.** `jobs/app.py::FINISHED_JOBS_DELETED`
is `DeleteJobCondition.ALWAYS`; it is the application's `worker_defaults`, so
every `run_worker_async` takes it, and `jobs/worker.py::amain` passes it to the
`Worker` it builds. procrastinate deletes on success and on the last failure and
keeps a job it will retry (`procrastinate/worker.py::_persist_job_status`). The
runtime's stalled-job release (`assistant_core/tasks/maintenance.py::_release_job`)
fails and deletes in one call. `procrastinate_events` cascades. Alembic
`2026_10_09_0001` deleted the rows already in `succeeded`, `failed`, `cancelled`
or `aborted`, and left `todo` and `doing` alone.

Nothing reads a finished row. `persistence/repositories/thread_job.py` reads
`todo` and `doing`, the runtime's sweep reads `doing`, `/health` reads
`procrastinate_workers`, and the tasks panel, the completion turn and stalled
task settlement read `background_tasks`, which a conversation delete cascades.

**No procrastinate record carries task arguments.**
`jobs/logging_filters.py::TaskArgumentsFilter` reads the `job` and `jobs` extras
procrastinate attaches, replaces each `call_string` in the message with
`task_name[id]`, cuts the `Result:` suffix, drops the `result` extra and keeps
`id`, `task_name`, `queue` and `status` of each job. It is attached to every
procrastinate logger and every root handler in the api and the worker.

# What was rejected

**Keeping finished rows to inspect them.** Each row held the request body, its
attached files and the researcher's VEuPathDB token, past every delete and purge.
The thread's own log and `background_tasks` already record what a turn and a
task did.

**Deleting queued jobs with the conversation.** A conversation delete or Clear
ALL data leaves a `todo` job alone: a durable job's `background_tasks` row and
its parked turn wait for it, and a conversation in Recently deleted can be
restored. A queued job is deleted once it has run.

**A regex over the formatted message.** The previous filter scrubbed only the
token key and left the chat body in the start line. The record already names its
job in structured extras, so the filter works on those.
