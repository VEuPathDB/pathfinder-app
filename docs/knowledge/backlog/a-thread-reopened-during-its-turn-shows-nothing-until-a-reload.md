---
type: Backlog
---

# A thread reopened during its turn shows nothing until a later reload

**What I did.** On plasmodb in the web app, sent a build request from a draft thread, waited 25 s (5 trace rows drawn, stop button visible), closed the tab, waited 40 s, and opened the thread's URL in a new tab of the same browser while the worker was still running the turn.

**What I got.** The reopened page requested the conversation and its snapshot and nothing else: `GET .../events/snapshot -> 200 {cursor: 220744, chunks: 1 (the user prompt), openMessage: null}`; no `GET .../events?after=` was ever issued (the api log holds none for the thread), local storage held no cursor or open message for the thread, and the page drew the user message only: 0 trace rows, no stop button, the rail reading "Waiting for the first stage of this investigation...". The worker finished the turn 10 s later ("chat turn completed", 155 genes) and the page stayed blank; only a full reload after completion drew 1 assistant message with 16 trace rows.

**Why that's wrong.** A researcher who closes the tab during a two-minute build and comes back sees their question with no answer, no progress and no way to tell a turn is running; they resend or give up, and a resend on a thread with a turn in flight is refused. The durable-thread promise (close the tab, come back, the turn is still there) does not hold for the most common way of coming back.

**Why it happens.** `useChatRuntime` (`apps/web/src/features/conversation/runtime/useChatRuntime.ts`, `reattach`) opens the tail only when the cursor store holds an open message, and the runtime's snapshot names `openMessage` only for a message whose `start` sits inside the snapshot, i.e. a turn suspended on a durable task; a running turn's snapshot ends at its prompt (`assistant_core/conversation/event_stream.py::latest_snapshot_boundary`), exactly as `PROTOCOL.md` section 2 says it must, so the snapshot's `openMessage` is null and the page never tails.

**Fix.** The protocol already says how a client follows a running turn: a snapshot followed by a tail from the snapshot's cursor. The thread view re-attaches when the snapshot's last chunk is a prompt envelope (a turn was opened and not terminated), as well as when an open message exists; a tail that answers 204 (no turn in flight, the prompt of a turn that died) falls back to the snapshot as section 4 requires, and the existing guard that a 204 must not end a turn the user starts meanwhile is covered by a test. The decision belongs to the client library if the snapshot reader can expose "turn in flight" from the chunks it already parses (`AssistantClient.snapshot` returning it beside `messages` and `cursor`), so the web app reads a fact rather than re-deriving it from message roles. Red first: a jsdom test mounting the thread on a snapshot whose last chunk is a `user-message` asserts one tail request from the snapshot's cursor and trace rows drawn from the tailed chunks.

**What you'd get.** The reopened tab shows the five trace rows already logged, the stop button, and the turn's progress and answer as they arrive; the same as the tab that started the turn.
