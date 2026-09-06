---
type: Decision
title: A revert is seen by re-snapshotting, not by a protocol signal
description: After a 204 from revert the client refetches the snapshot and replaces its message list before sending the edit; a truncation or thread-replaced chunk in PROTOCOL 1, turning revert into fork-as-new-thread, and a local truncation of the client's own list were all rejected.
tags: [chat, protocol, revert, client-state]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# What was decided

`POST <thread>/revert-to-message` answers 204 and says nothing about what it
deleted. The client treats that 204 as "your copy of this thread is stale":
`EditComposerBranchOrRevert` invalidates the snapshot query and awaits the
refetch, then sets the pending submission and remounts the thread, so the list
the user sees and the list the next turn is built from are both the
re-snapshotted log. The edit is sent after that refetch, never before.

The log stays append-only in the protocol's terms. PROTOCOL 1 grows no chunk
kind, and a client that only tails is unchanged by this decision.

# Why not a truncation signal in PROTOCOL 1

A `thread-truncated` or `thread-replaced` chunk would let a tailing client learn
about a revert without polling, and it is the honest fix for the invariant the
thread-surgery audit records (I1 and I3): a reader connected across a revert
sees a snapshot and a tail disagree. It was rejected for this batch because it
is a protocol version, not a client patch: it needs a producer in
`assistant_core`, a reducer rule for "drop everything at or after this cursor",
a conformance case in `assistant-platform/packages/assistant-client-ts`, and an answer for the
cursor that now points past the end of the log. The re-snapshot costs one
request and needs none of that.

# Why not fork-as-new-thread

Making Revert a fork that starts a fresh thread needs no new signal either, and
it never deletes anything. It was rejected because it changes what the user
asked for: "Revert this chat" is a request to shorten this chat, and the
conversation list would grow a thread per undo. It stays on the table as the
PROTOCOL 1.4 alternative in
`docs/design/2026-08-28-thread-surgery-audit.md`.

# Why not truncate the client's list locally

Cutting the local message array at the target id is one line and needs no
request. It was rejected because the client would be guessing the server's cut:
`revert.py` cuts on `(created_at, id)` and also deletes notes, task rows and
checkpoints, and a message the client holds is not proof of the row the server
kept. The snapshot is the server's answer to "what is this thread now", so the
client asks it.
