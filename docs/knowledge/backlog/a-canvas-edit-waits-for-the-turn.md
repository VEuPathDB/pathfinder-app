---
type: Backlog
title: A canvas edit waits for the turn
description: POST /api/v1/conversations/{id}/operations applies a canvas edit while a turn of the same thread is running, so the canvas commit and the turn's commit each write a whole tree built from their own base and the later one drops the other's edit; refuse or queue a canvas edit while a turn, a parked approval or a durable task holds the thread.
tags: [canvas, strategy, concurrency, threads]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A canvas edit waits for the turn

## What happens

`services/conversations/strategy_ops.py::apply_operation` holds the thread's strategy write
lock (`strategy:<conversation id>`) for its read, its WDK push and its write. A chat turn's
strategy writes (`ai/lead/edit_dispatch.py`, `services/strategies/spec_build.py`,
`services/strategies/materialize.py`) run in the worker and take that lock only for the
database write (`services/strategies/persist.py`), not across their read and push. The
route checks nothing else: `services/conversations/thread_busy.py::claim_settled_thread`,
which refuses a thread with a running turn, a parked approval or an active task, is called
only by fork and revert. So an edit sent from the canvas while a turn edits the same
strategy is applied, and the two commits each write a whole tree from their own base. The
strategy line (`docs/knowledge/decisions/a-request-on-a-wdk-strategy-waits-in-its-line.md`)
keeps WDK from restoring an old tree, but not this lost update. Not measured: whether the
web app sends such an edit; the server does not refuse one.

## Done when

The route refuses an edit with 409 while `claim_settled_thread` names the thread busy, or
queues it behind the turn, and the canvas says why; an integration test sends an edit
during a running turn and finds the turn's edit and the canvas edit both kept, or the
canvas edit refused.
