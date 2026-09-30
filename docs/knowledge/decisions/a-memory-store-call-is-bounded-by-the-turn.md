---
type: Decision
title: A memory-store call is bounded by the turn, and neither call fails the turn
description: Retrieval at Lead entry and the auto-write in finalize_turn run under memory_store_timeout_seconds (default 30); exhaustion raises MemoryStoreTimeoutError, which retrieval logs and degrades to no memories. The auto-write runs after the reply is on the wire, so any failure of it is logged and dropped and the turn ends with its reply; re-raising it was measured replacing a finished reply with a stop message. An unbounded await was measured parking a test run for the full 600 s ceiling. The store's batch task is also ended with the store, so a closed store leaves nothing pending.
tags: [memory, langgraph, jobs, worker, reliability, chat]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-29T00:00:00Z }
status: stable
---

# What was decided

A turn touches the LangGraph store twice: `ai/graph/_lead_turn.py::retrieve_memories`
at Lead entry and `auto_write_memories` in `finalize_turn`. Both now run inside
`assistant_core.memory.deadline.memory_store_deadline`, an `asyncio.timeout`
whose window is `memory_store_timeout_seconds` (default 30). Exhaustion raises
`MemoryStoreTimeoutError`, which carries the operation and the window.

**Retrieval degrades**: it logs a warning naming the thread and returns `[]`,
and the turn runs on the user's prompt alone. **The auto-write is dropped**:
`ai/graph/nodes.py::_write_the_notes` logs any exception it raises, the
timeout included, and `finalize_turn` ends the turn as it would with no
notes. The saved gene sets stay on the state, so the next verified turn
offers their notes again.

The invariant: once the reply part is written, no later step of the turn's
finalisation changes what the researcher sees. The auto-write is a write the
researcher never asked for and never sees confirmed, so its failure has no
sentence to put on screen.

# The evidence that reversed the first rule

The first version of this decision let the auto-write fail loudly: it
re-raised `MemoryStoreTimeoutError`, so `run_turn` wrote `error`,
`data-turn-failed`, `finish` and `done`. On a trichdb build turn the event log
held the facts part and the whole reply, then an `error` part with "This turn
stopped before it could answer. Ask again." and `finish: error`. The worker
logged the auto-write timing out at 30 s in `store.aput`, one minute after a
DNS failure had refused a connection. The researcher was told to ask again
under a complete answer, and asking again rebuilds a strategy that exists.
The reason the first rule gave, a memory the user believes was saved, does not
hold for a write the user did not request.

# Why the store was the call that could hang

Every other outbound call of a turn is bounded: the WDK client sets
`httpx.Timeout` (30 s per component request, 120 s to the portal), the
embeddings client sets 60 s with five retries, and the model clients carry the
provider default. The store did not. `AsyncBatchedBaseStore.aget/asearch/aput`
put an operation on a queue and `await` a future that only the background batch
task resolves, and `AsyncPostgresStore.from_conn_string` opens one plain
`AsyncConnection` with no statement timeout, so a connection that stops
answering parks the turn with nothing to end it.

Measured: `tests/unit/ai/graph/test_memory_deadline.py`, written against a
store whose `asearch` never resolves, ran for the full 600 s command ceiling
before the deadline existed and finishes in 1.26 s with it. The backlog item
this closes recorded turns of 939 s, 1039 s and 1909 s against a 12.7-29.6 s
normal band for the same prompt.

# The batch task ends with the store

`lifespan_memory_store` is a per-turn `async with`, and the store's background
batch task was not part of it: `AsyncBatchedBaseStore` cancels the task only
from `__del__`, so every turn left a task the loop reported as
"Task was destroyed but it is pending" at `langgraph/store/base/batch.py:330`,
which is the line the backlog item quoted. The lifespan now cancels and awaits
that task before the connection closes, so the store owns its task for exactly
as long as the turn owns the store. The task is private to LangGraph and there
is no public shutdown, which is why `_task` is read directly.

# What was rejected

**One long-lived store per worker process.** It would remove the per-turn
`setup()` round trip, but it also keeps one Postgres connection open across
turns, and a connection that dies quietly is the failure this item is about. A
per-turn store gets a fresh connection every turn, and the deadline covers the
turn that is unlucky.

**Bounding the store inside `MemoryStore`.** The wrapper would then own a
policy that differs per call site: retrieval degrades and the auto-write does
not. The deadline sits where the decision about the failure is made.

**Failing the turn on an auto-write timeout.** Measured above: it replaces
a finished reply with a stop message. A lost note costs one retrieval later;
a lost reply costs a rebuilt strategy.

**Catching only the timeout and the builtin I/O errors.** An embedding client
error is none of them, and it reaches the same place after the same reply.
