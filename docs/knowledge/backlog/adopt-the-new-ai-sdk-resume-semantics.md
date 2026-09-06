---
type: Backlog
title: Adopt the new ai SDK resume semantics
description: ai 6.0.250 made resumeStream a fresh response instead of a continuation of the held assistant message, which is the opposite of what PROTOCOL.md section 6.1 requires of a turn suspended on a durable task; the client is pinned below that release until it reduces the resumed tail itself.
tags: [assistant-client, protocol, ai-sdk, durable-tasks, packaging]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: open
---

# What is wrong

`@pathfinder/assistant-client` pins `ai` to `6.0.154` and caps its peer range
below `6.0.250`. That release carries "Prevent `resumeStream` from copying the
previous assistant message into the resumed response": `AbstractChat` now builds
the resumed response's state with `lastMessage: undefined`, so a resumed stream
starts an empty message with a generated id instead of continuing the assistant
message the client already holds.

`PROTOCOL.md` section 6.1 requires the opposite. A turn suspended on a durable
task closes with `finish`; the gap then carries that task's
`data-task-progress` and `data-task-completed`, which belong to the suspended
turn's message; only then does a `start` open the continuation turn.
`DurableChatTransport` places the gap chunks by letting the SDK continue the
held message, and holds back a `start` that names a different message so no part
crosses the boundary.

Measured on a copy of the platform repository with `ai` at `6.0.271`:

```
FAIL tests/conformance/resumedTurn.test.ts
  > reads the continuation as its own message, and copies no part into it
  > finds the boundary from the message a reload already holds
Test Files  1 failed | 19 passed (20)
Tests  2 failed | 260 passed (262)
```

Both failures are the same shape: the gap's two parts land on a new assistant
message with a generated id (`TDt1mM4XG1Sqe3jZ` in one run) instead of joining
the suspended message.

# Why it is not just a version bump

Emitting a synthetic `start` naming the held message does not fix it. On a
resumed stream `state.message` is empty, and the SDK's `write` replaces the last
message with that state when the ids match, so the parts the client already held
would be dropped rather than kept.

Placing the gap correctly under the new semantics means the client reduces the
resumed tail itself and merges it into the message it holds, rather than handing
the tail to the SDK's message builder. That is a change to
`DurableChatTransport` and `resumeDurableThread`, and it needs the reduction
rules of section 9 applied on the client's side of the seam.

# What done looks like

`assistant-platform: packages/assistant-client-ts/package.json` names `ai` at the
current 6.0.x with no upper bound in the peer range, its 262 conformance cases
pass there, and `apps/web` runs the same version through `@ai-sdk/react`. The
pin's paragraph leaves `assistant-platform: README.md` and
[the grouping decision](../decisions/the-assistant-platform-is-a-grouping.md).
