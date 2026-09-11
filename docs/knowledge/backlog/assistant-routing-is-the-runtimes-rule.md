---
type: Backlog
title: Which assistant answers a turn is the runtime's rule, kept in the app
description: ai/conversation/assistant_routing.py resolves a turn's assistant from the registry and the conversation row and refuses a mismatch, naming no gene, strategy, search or phase; only the two error types are the app's, so every deployment of the runtime has to re-author the rule.
tags: [assistants, routing, assistant-core, wrong-repo]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Read `apps/api/src/pathfinder/ai/conversation/assistant_routing.py` in full and
listed its callers and the names it uses.

# What I got

47 lines, two functions. `resolve_assistant` wraps
`AssistantRegistry.resolve` and turns `UnknownAssistantError` into a 404.
`resolve_turn_assistant` reads `conversation_assistant_id(conversation_id)`
from `assistant_core.conversation.authz`, returns the requested id or the
registry default for a thread that does not exist yet, and raises
`AssistantMismatchError` when a request names an assistant other than the one
the thread was created with.

Everything it touches is the runtime's except two imports from
`platform/errors.py`: `AssistantNotFoundError` (404,
`ErrorCode.ASSISTANT_NOT_FOUND`, line 182) and `AssistantMismatchError` (409,
`ErrorCode.ASSISTANT_MISMATCH`, line 197). Three transport modules call it:
`routers/chat.py:8`, `routers/conversations/crud.py:10`,
`routers/conversations/wdk_import.py:5`.

# Why that's wrong

[The orchestration belongs to the assistant, not to the
platform](../decisions/the-orchestration-is-the-assistants.md) states that the
runtime resolves one assistant per turn from a registry keyed by the
conversation row. The code that does the resolving lives in the app instead, so
a second deployment of the runtime must rewrite the rule, and its 404 and 409
are that deployment's opinion. Two implementations of "an existing thread keeps
its assistant" will not stay identical.

# Why it happens

`resolve_turn_assistant` was written beside the routes that call it rather than
beside `AssistantRegistry`.

# Fix

Library first, in `ai-assistant-platform`: move both functions into
`assistant_core/registry.py`, raising `UnknownAssistantError` and a new
`AssistantMismatchError` carrying the requested and existing ids. Then here:
delete the module, call the runtime's resolver from the three routers, and map
the two runtime exceptions to the existing `AppError` subclasses in the
transport error handlers so the wire keeps its 404
`ASSISTANT_NOT_FOUND` and 409 `ASSISTANT_MISMATCH`. Take it at the library's
next tag.

# What you'd get

One implementation of the routing rule, tested where the registry is tested,
and an app that owns only how the refusal is rendered on the wire.
