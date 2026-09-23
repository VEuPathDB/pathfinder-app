---
type: Decision
title: The thread title is the last chunk before a turn finishes
description: run_turn writes data-conversation-title immediately before the turn's finish chunk, awaiting the title task there under a 15 s ceiling, instead of writing it on the first graph chunk that arrives after the task reports done. Emitting right after start, and comparing the golden fixture by presence instead of by position, were rejected.
tags: [chat, sse, turn-runner, testing, protocol]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What was decided

`ai/conversation/turn_runner.py` writes `data-conversation-title` at one point
of every turn: after the epilogue, immediately before the `finish` chunk. The
title task is awaited there under `_TITLE_WAIT_SECONDS` (15), and a title the
model does not produce inside that window is dropped with a warning, so a slow
title model cannot hold the turn open.

The turn therefore always ends `data-conversation-title`, `finish`, `done` when
it names the thread, and `finish`, `done` when it does not.

Until the title arrives, the web client shows the thread's first message, cut
to 60 characters on a word boundary, as a provisional name
(`apps/web/src/lib/conversations/provisionalName.ts`) in the sidebar row and the
strategy canvas; the name the server writes replaces it once it is non-empty.

# Why the position had to be decided at all

The runner used to carry the title opportunistically: `_handle_custom` checked
`title_task.done()` on every chunk the graph streamed and wrote the title on the
first one that arrived after the task finished. The position was then a
scheduling outcome. The same prompt on the same build, with only the cost of the
title task changed, puts the chunk at index 4 when the title is ready
immediately and at index 7 when it takes 0.4 s, in a turn of 24 chunks that is
otherwise identical. The golden fixture
`tests/integration/chat/_fixtures/chat_sse_golden_simple_turn.json` asserts the
whole list in order, so the fixture recorded a machine's timing and failed on
another one with no product change behind it.

# Why before `finish`, and not after `start`

`PROTOCOL.md` states no position for `data-conversation-title`
(`assistant-platform: packages/assistant-core/src/assistant_core/PROTOCOL.md`,
sections 5.2 and 6). It states a position for the two other conversation-level
parts, `data-turn-stopped` and `data-turn-failed`, and both are "before
`finish`". A client reads the part by kind: `useChatRuntime.ts` invalidates the
conversation list on it wherever it lands, and `coreDataParts.ts` maps it to
`noRender`. Before `finish` follows the rule the protocol already states for its
neighbours.

After `start` was rejected because it is the one position that costs the user
time. The title comes from a separate model call, so emitting it first means
every turn waits for that call before the agent's first token. Before `finish`
the title is generated in parallel with the whole turn and is almost always
ready when the wait begins.

# What else was rejected

**Comparing the golden by presence and payload instead of by position.** It
silences the test without deciding what the wire does, and the position stays
whatever the scheduler makes it, which is a fact no client can rely on and no
fixture can pin.

**An unbounded await.** The previous post-graph path already awaited the title
task with no ceiling, so a hung title model held `finish` for as long as the
model took. The ceiling is what makes the defined position safe to await.

# What the ceiling costs

15 s tightens the only bound the title call otherwise has: `build_model_settings`
gives every provider a 900 s request timeout and the title agent is built with
`retries=1`, so an unbounded await could hold `finish` for roughly half an hour.
The number is a deadlock ceiling, not a measured budget, and a fired ceiling
costs the thread nothing permanent: `run_turn` starts a title task on every turn
whose user text is non-empty, and `name_conversation_if_unnamed` writes only when
the thread has no name, so the next turn names it. `POST /conversations/{id}/begin`
also generates a title of its own when the thread is created.

Writing the title is bounded the same way. `name_conversation_if_unnamed` waits
at most 10 s (`LOCK_WAIT_SECONDS`) for the thread's strategy lock and its local
writes (the thread, the stored strategy, the auto-imported gene set), releases
the lock, and then sends the name to WDK under its own 10 s bound
(`naming.WDK_RENAME_SECONDS`), catching every failure there. `_write_title`
catches any failure of the write and logs it, so the worst case before `finish`
is 15 + 10 + 10 s, and a write that fails or times out costs one title chunk:
the next turn names the thread, and the next push sends the name to WDK.

# What would change this

The rule belongs in the protocol, not only in this runner. `PROTOCOL.md` states a
position for `data-turn-stopped` and `data-turn-failed` and none for
`data-conversation-title`, so a reader reads the silence as "anywhere" and the
next assistant built on this runtime is free to place the part elsewhere. The
proposal for the platform is one sentence in section 6 beside its two
neighbours - "A turn that names its thread writes `data-conversation-title`
before `finish`" - plus the version-table row. This repository cannot change
`PROTOCOL.md`; the platform bundle carries the card. A protocol that states a
different position replaces this decision.
