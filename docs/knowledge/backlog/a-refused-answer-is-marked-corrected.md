---
type: Backlog
title: A refused answer is marked corrected
description: pydantic-ai 2.54 hands an output tool's retry to handle_output_tool_result, and assistant-core's PhaseStreamEmitter marks only function tool retries corrected, so a final answer the turn contract sends back reads as a failed call in the trace; release assistant-core with the output override and take the pin.
tags: [runtime, trace, assistant-core]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A refused answer is marked corrected

## What happens

`assistant_core/conversation/vercel_adapter.py::PinnedVercelAIEventStream` overrides
`handle_function_tool_result` to send a `corrected` tool summary for every `RetryPromptPart`.
pydantic-ai 2.54 dispatches the retry of an output tool (`final_result`) as an
`OutputToolResultEvent` to `handle_output_tool_result`, which the class does not override.
The trace row of a refused answer then has no summary status, and the client reads a failed
call as `error`. Two browser tests assert the `corrected` row: "A count the facts do not
show is taken out of the reply" and "An open value asked in prose is corrected to the
question card" (`apps/web/e2e/uat/faults.spec.ts`).

## Done when

assistant-core overrides `handle_output_tool_result` with the same corrected summary, with a
unit test that streams an `OutputToolCallEvent` and its retry; a release is tagged, the pin
in `apps/api/pyproject.toml` moves to it, and both browser tests pass.
