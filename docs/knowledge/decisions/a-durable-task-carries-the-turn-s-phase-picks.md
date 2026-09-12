---
type: Decision
title: A durable task row carries the deferring turn's phase picks, so an override stays request-scoped
description: background_tasks gains a phase_overrides JSONB column, written from a per-turn context variable at deferral and read back when the worker opens the completion turn. Persisting the picks on the conversation was rejected, because it would turn a per-request override into a thread setting.
tags: [durable-tasks, completion-turn, models, cost]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# What was decided

`POST /api/v1/chat` carries `phaseModels` and `phaseReasoning`, and
`ChatRequestBody` refuses a role no installed assistant runs a model for and
validates the model ids against the catalog. `run_turn` publishes the validated pair on
`assistant_core.platform.context.phase_overrides_ctx` for the length of the
turn. `create_background_task` reads it and stores it on the
`background_tasks.phase_overrides` column (migration `2026_08_30_0002`).
`assistant_core.tasks.completion_turn` reads the row back and hands the picks
to the host, and `jobs/completion.py` rebuilds the completion turn's
`ChatRequestBody` from them, so `TurnContextRequest` receives the same picks
the suspending turn ran under.

The picks travel by context variable rather than by argument because the
deferring caller is `@durable_tool`, which the runtime owns and which reads no
host table; the WDK token takes the other seam, a `DurableJobState` the host
subclasses.

The value is stored as a plain JSON object. A role is a plain string that the
tier presets name, so the roles are checked on the way in and the column holds
what both ends agree on.

# What was rejected

**Persisting the picks on the conversation.** Every turn on the thread would
then read one set, and the completion turn would need no lookup. It was
rejected because it changes what a per-request override means: a body field
that today applies to one turn would silently become a thread setting, and a
researcher who pins a model for one question would keep paying for it on every
later question. The defect is that a request's picks do not reach the turn
that finishes the request's work, and the row that already represents that
work is where they belong.

**Reading the picks from the checkpoint.** The parked state is written by the
runtime package, which names no phase and no role. Putting a PathFinder
concept in `TurnState` to solve a PathFinder wiring problem inverts the
layering the runtime split established.

# The consequence, stated

Both halves of one investigation resolve the same model and the same reasoning
effort, so a per-phase comparison is not silently mixed across two models. A
task deferred before the column existed reads the empty map and its completion
turn resolves the configured tier, which is what it ran under. A model id that
leaves the catalog while a task is in flight fails the completion turn, and
`safe_completion_turn` records that failure on the task row rather than
answering under a model nobody picked.

# Anchor

`apps/api/src/pathfinder/jobs/completion.py::open_completion_turn`, pinned by
`apps/api/src/pathfinder/tests/integration/jobs/test_completion_turn_phase_overrides.py`
and
`apps/api/src/pathfinder/tests/integration/persistence/test_task_phase_overrides_migration.py`.
