---
type: Decision
title: A sub-agent's approval is answered inside that sub-agent
description: An approval-required tool called inside a phase sub-agent is forwarded to the client as its own tool part; the Lead's dispatch call is deferred with CallDeferred, and the user's answer re-enters the same sub-agent run with DeferredToolResults(approvals=...) before the Lead resumes with the finished delta.
tags: [agents, sub-agents, approvals, safety, chat, sse]
generated: { by: claude-code/opus-5, at: 2026-08-17T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-17T00:00:00Z }
status: stable
---

# What was decided

The tool that needs approval is the tool the user answers, wherever it runs.

`optimize_search_parameters` (verification) and `delete_step` (execution) carry
`requires_approval=True`, so a sub-agent run that calls one ends in
`DeferredToolRequests` instead of its typed delta. That run is now
suspended rather than discarded:

1. **The inner call becomes a tool part.** `sub_agent_stream` emits
   `tool-input-start`, `tool-input-available` (the real arguments) and
   `tool-approval-request` for the inner `tool_call_id`, through the same writer
   the sub-agent step chunks use. The approval id IS the inner tool call id, so
   the answer comes back naming it. The generic Approve/Deny card renders it
   with no per-tool work.
2. **The Lead's dispatch call is deferred, not answered.** The wrapper
   (`verify_strategy`, `recover_failed_steps`, `frame_problem`) stashes the
   suspended run on `LeadDeps` and raises `CallDeferred`, so the Lead run ends
   with `DeferredToolRequests(calls=[<dispatch call>])` and the whole turn is
   checkpointed on `PendingApproval.sub_agent`.
3. **The answer re-enters the sub-agent first.** The next turn replays the
   sub-agent's own message history with
   `DeferredToolResults(approvals={inner_id: True | ToolDenied(...)})`, streams
   the continuation, and closes the inner tool part with
   `tool-output-available` or `tool-output-denied`.
4. **Then the Lead resumes.** The finished delta is handed back as
   `DeferredToolResults(calls={dispatch_call_id: delta})`, which is exactly what
   the wrapper would have returned, so the rest of the turn is unchanged. A
   sub-agent that asks for a second approval re-defers without running the Lead.

The wrapper body is one function per dispatch (`run_frame`, `run_recovery`,
`run_verification`), used by both the direct call and the re-entry, so the
post-processing (spec sync, build re-sync, verification digest) cannot drift
between them.

# The dispatch call is always resolved

pydantic-ai re-executes a deferred tool call that the resume gives no result
for, so a Lead run resumed against an unresolved dispatch runs the whole
sub-agent again, and the execution role re-applies its edits. Three rules keep
that from happening:

- **A typed reply resolves the card.** The user can answer by typing rather than
  clicking. If the text is nothing but an approval phrase (the same strict
  whitelist that lets a short affirmative past the injection scanner,
  `assistant-platform: packages/assistant-core/src/assistant_core/capabilities/input_screening.py`), the pending inner calls are
  approved. Otherwise they are denied with "The user replied instead of
  answering the approval." and the text is delivered to the Lead as the user's
  next message in the same run, after the tool returns. A typed reply is
  recognised by `PendingApproval.user_message_id`: answering a card leaves the
  turn's user message id untouched, so a different id is a new message.
- **A turn that resolves nothing is a no-op.** No click, no typed message and no
  answer naming the dispatch call means the card stays and no sub-agent runs.
- **One suspended run per turn.** The suspended runs are stashed by dispatch
  call id, and a response that defers two of them raises
  `ConcurrentSubAgentApprovalsError` naming both. Deferring them in order would
  leave the second call unresolved on the resume, which is the re-execution this
  section exists to prevent; a loud failure is better than a silent re-run.

A dispatch outranks the Lead's own `consult_user` approval in the same response,
because only the dispatch holds a suspended run. The consult call is re-raised
by pydantic-ai on the resumed run, and an answer to it that arrived meanwhile is
passed through with the dispatch's result, so neither is lost.

# What was rejected

**Re-asking through the Lead's `consult_user`.** The sub-agent would stop, the
Lead would ask a free-text question, and then re-dispatch. It loses the tool's
own identity and arguments (the card would show a question, not the sweep's
target and controls), it asks the user twice for one decision, and the tool call
is re-decided by a model instead of resumed, so the thing that runs is not the
thing that was approved.

**Dropping `requires_approval` from the sub-agent tools.** Honest about the old
capability and one line to write, but it moves the guard away from the call
site: a ~15 minute parameter sweep would start unasked, and two destructive
strategy edits would run with no confirmation at all.

# What holds it

Unit tests drive the real verification and execution toolsets with scripted
models: the approval chunks carry the inner call id and its arguments, the turn
ends with `PendingApproval(phase="verification", sub_agent=...)`, an approval
runs the inner tool exactly once and the Lead answers, a denial finishes the
sub-agent with the tool never invoked, and a second approval defers the turn
again. Usage is recorded once per half under the dispatch's call id, so neither
half is lost or double-counted.
