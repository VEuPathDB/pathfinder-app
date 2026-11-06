---
type: Decision
title: Chunk suppression follows the call, not a list of chunk types
description: The sub-agent suppression list enumerated the chunk types seen on the happy path, so the error-path chunk leaked an orphan the AI SDK throws on. Suppression is now keyed on what a chunk refers to, and a guard test fails if a new chunk type goes unclassified.
tags: [chat, sse, crash, architecture]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# The crash

`Response failed: No tool invocation found for tool call ID "call_...".`
Reported on branching, reverting, cancelling, and at random in long runs.

It is thrown by the **Vercel AI SDK client**, in `ai/dist/index.mjs`, when a
tool output names a call the client never saw announced. It never reaches a
backend log, which is why it read for so long as a silent provider rejection --
and why an earlier decision misattributed it to OpenAI.

# The cause

A Lead sub-agent dispatch (`frame_problem` and friends) is rendered as a
`data-sub-agent-call` card, and its native tool chunks are suppressed so the raw
tool card does not render alongside it. `_SUPPRESSED_SUB_AGENT_CHUNKS` listed
five types -- every one of them observed on the **happy path**.

`ToolOutputErrorChunk` was not among them, because it only appears when a run
raises: pydantic-ai closes each pending tool call with a synthesized tool output
(`ui/_event_stream.py`). So the success output was suppressed and the failure
output was not, for a call whose inputs were suppressed either way. The client
had nothing to attach it to and killed the whole response.

# What was decided

Two things, because fixing only the first would have traded a crash for a lie.

1. **Suppression is keyed on what a chunk refers to.** `_TOOL_CALL_CHUNKS` names
   every chunk carrying a `tool_call_id`; anything referring to a claimed
   dispatch is suppressed whatever its type. `_CHUNKS_EXEMPT_FROM_SUPPRESSION`
   holds the approval chunks, which must reach the user or the turn waits on a
   question nobody sees.

2. **`sub_agent_result_failed` reads both failure outcomes.** A dispatch whose
   `ToolReturnPart` has `outcome` `failed` (an interrupted run) or `retried` (a
   call handed back to the Lead) shows "failed". Reading only one of them
   would render the other as **completed** -- a false success, worse than the
   crash it replaced.

# What keeps it fixed

`test_every_tool_chunk_type_is_classified` introspects pydantic-ai's
`response_types` for every class with a `tool_call_id` field and fails if one is
neither suppressible nor deliberately exempt. The original omission was invisible
until it crashed a user's turn; now a new chunk type in a future pydantic-ai
fails a test instead.

# Evidence

Same mega prompt, in the browser, before and after. The reported error changed
from the SDK's fabricated `No tool invocation found for tool call ID` to the
real condition (`tool_calls_limit of 60`). Chunk-level check of the turn:

| tool call | announced natively | announced as card | native output |
|---|---|---|---|
| ordinary tool | yes | -- | yes, paired |
| sub-agent dispatch | no | yes | **none** |

# What this does not fix

FRAME cannot bind a nine-criterion problem inside its 60 tool-call budget
(`PHASE_USAGE_LIMITS`). That is now reported honestly instead of crashing, but
the budget is a fixed constant that does not scale with the declared work, and a
run that hits it discards the criteria it already bound.
