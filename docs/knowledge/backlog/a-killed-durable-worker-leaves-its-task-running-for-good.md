---
type: Backlog
---

# A killed durable worker leaves its task running for good

**What I did.** Traced what closes a durable call when the worker running it dies, the way the
stalled-job sweep closes a chat turn. Read the four writers of a `background_tasks` row
(`assistant_core/tasks/runner.py:182,188,235,246,273,275`), the sweep
(`assistant_core/tasks/maintenance.py:62-140`) and the two readers a thread shows the row
through: `has_active_task` (`assistant_core/tasks/service.py:19-37`) and `list_task_rows`,
which `GET /api/v1/conversations/{id}/tasks` serves.

**What I got.** Every terminal write runs inside the job itself: `mark_failed` at
`runner.py:188` and `235` is in that function's own `except`, and `mark_failed`/`mark_complete`
at `runner.py:273,275` run after the completion turn returns. A SIGKILLed worker reaches none
of them, so the row stays at the `mark_running` value from `runner.py:182`. The sweep releases
the job, but its stream closer returns at once for a job that is not a chat turn:
`maintenance.py:113` reads `if job.task_name != CHAT_TURN_TASK: return`. So the thread is left
with a `background_tasks` row at `running`, an unterminated chunk log, and a procrastinate job
row at `failed`.

**Why that's wrong.** `_ACTIVE_TASK_STATUSES` is `{"pending", "running", "resuming"}`
(`service.py:19`), so `has_active_task` answers `True` for that row for good. The tail route
(`transport/http/routers/conversations/events.py`) streams whenever that reader says a task is
active, so the thread reopens as work in progress and holds one database `LISTEN` connection
per open tab, with no chunk ever coming. The tasks rail (`rail/TasksPanel.tsx`, from
`GET /api/v1/conversations/{id}/tasks`) shows the call as still running, and the enrichment or
compute result the user was waiting for never arrives and is never reported as failed. The
turn that parked on the call keeps its tool part unanswered, so the thread cannot be resumed
by sending another message either.

**Why it happens.** `_close_stalled_turn` was written for the chat-turn job alone
(`maintenance.py:111-114`), and nothing else fails a `background_tasks` row from outside the
job that owns it.

**Fix.** The sweep settles a released durable job the way the job would have settled itself:
read the task id from the job's stored kwargs (`DurableTaskPayload`), `mark_failed` that row
with the released job's error text, and announce the failure on the thread so the parked turn
is answered and the log reaches `done`. The change is the runtime's
(`VEuPathDB/ai-assistant-platform`, `assistant_core/tasks/maintenance.py`), not this
application's, so it ships in a release this repository then pins.

**What you'd get.** A thread whose durable worker was killed reports the call as failed within
the dead-heartbeat window, the rail row turns red instead of spinning, the tail answers 204
and the thread reopens static with a failure the user can act on.
