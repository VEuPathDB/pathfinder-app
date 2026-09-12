---
type: Backlog
---

# A tail on a dead turn streams forever

**What I did.** Read the tail route that serves `GET /api/v1/conversations/{id}/events?after=N` (`apps/api/src/pathfinder/transport/http/routers/conversations/events.py`) against the client rule the protocol now states: a client that reads a snapshot whose last chunk is a prompt envelope opens a tail from the snapshot's cursor, and a `204 No Content` answer means no turn is in flight. Compared it with the portal thread `9f75eb09-33b5-46c2-9e05-646b1d76356d`, whose worker was killed mid-turn (exit 137) before writing a `finish` or a `done`.

**What I got.** The route computes `turn_in_flight = tip is not None and tip[1].get("type") != "done"` (`events.py:37`). When the log's last chunk is the prompt of a turn whose job never ran or died before writing, the tip is that prompt, never `done`, so the route always streams: `replay_and_tail` replays nothing and holds a `LISTEN` connection with keepalive frames until the reader leaves. A tab that reopens such a thread draws a running turn that never ends.

**Why that's wrong.** Before the client rule, a dead turn reopened as a static thread; after it, the same thread shows a turn that never finishes and holds one database `LISTEN` connection per open tab. The normal error path is unaffected (`turn_runner.py` writes `finish` and `done` on `finish_reason="error"`); the hard-failure path (worker killed, queue drained, job never picked up) is the one that hangs.

**Why it happens.** The route derives "in flight" from the log's tip alone; the host knows more (whether a `chat_turn` job for the thread is queued or running), and the protocol's `204` clause assumes the host uses that knowledge.

**Fix.** The events route answers `204` when the tip is a prompt envelope and no `chat_turn` job for the thread is queued or running (the procrastinate job table names the conversation); the client and the app then need nothing further. Red first: a route test with a prompt-tip log and no job answers 204; the same log with a running job streams.

**What you'd get.** A thread whose turn died reopens as a static thread with its prompt, and the composer is free; a thread whose turn is running reopens streaming.
