---
type: Decision
title: A durable tool is a deferred tool, so its completion continues the turn instead of replaying it
description: "@durable_tool creates the background_tasks row, defers the job, records the deferral on the deps and raises CallDeferred; the run ends with every durable call of the step parked on the state and the worker opens a NEW turn, once the last of their tasks reports, carrying DeferredToolResults for all of them. LangGraph interrupt() inside the node was rejected: a resume re-executes the node from its first line, so every model call and tool side effect before the interrupt runs again."
tags: [durable-tasks, resume, langgraph, pydantic-ai, assistant-core, protocol]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
status: stable
---

The mechanism is the runtime's: one `declare_durable_tool` binds the decorator,
the procrastinate job and the worker-side body to one name
(`assistant-platform: docs/knowledge/decisions/a-durable-tool-is-declared-once.md`
and `.../conventions/durable-background-tasks.md`). This page records what
PathFinder declares and what the Lead does with a parked call.

# What was decided

A durable tool ends its run the way an approval does. `@durable_tool` creates
the `background_tasks` row (which records the pydantic-ai `tool_call_id` the
result will answer), defers the procrastinate job, records a `DurableDeferral`
on the agent's deps, writes `data-background-task-started` through the graph's
stream writer, and raises `CallDeferred`. The run's output is
`DeferredToolRequests`, the turn parks a `PendingDurableCall` on the state
beside `pending_approval`, and the turn closes with `finishReason: "other"`.

**One model step may call several durable tools, and the park records all of
them.** `PendingDurableCall.durable_calls` holds one `DurableCall` per deferred
call: its id, the name and arguments the model used, its task, and the name the
durable tool registered under. pydantic-ai requires a result for EVERY
function-kind call of the response a run re-enters, so a resume that answers
one of two calls is refused with `Tool call results
need to be provided for all deferred tool calls`. A sibling that settled inside
the same step needs nothing: its `ToolReturnPart` is in the captured history,
and `_handle_deferred_tool_results` turns that into the `'skip'` sentinel
itself.

When a job finishes, the worker announces `data-task-completed`, stores the
result on the task's row, and opens a NEW turn ONLY when every task of the
parked step reports. The turn carries `TurnRequest(durable_results=...)`, read
back from those rows, and resumes the parked run from `prior_messages_json`
with `DeferredToolResults(calls={each id: ToolReturn(...)})`. An earlier
arrival writes its completion chunk and stops, its row holding its result at
`result_ready`; the turn that finally opens marks every row it answered
complete. Each tool's declared `chunks_from_result` runs on that turn against
its own task and call id, so each summary and figure lands beside its own
output part. Durable calls inside a sub-agent park the dispatch call with the
sub-agent's `messages_json`, and the completion turn re-enters that run first,
exactly as an approval does.

Two sub-agent dispatches that both park durable calls in one Lead response are
still refused (`ConcurrentDurableDispatchError`), for the reason two concurrent
approvals are: one suspended run is checkpointed per turn.

# What was rejected

**LangGraph `interrupt()` inside the node.** The tool called `interrupt()` from
inside the agent run, inside the `lead` node, and the worker resumed with
`Command(resume=...)`. LangGraph's contract is that a resume re-executes the
node from its first line and matches resume values to `interrupt()` calls by
their order in the node. The whole Lead run therefore started over: the model
was called again, tool side effects before the durable call ran again, and the
stored result was handed to whichever call the replay reached. Measured on the
febrile-versus-normal DESeq prompt: one prompt produced two EDA analyses, three
compute jobs, two `create_eda_step` failures and a turn that never wrote
`done`.

**Answering each task on its own turn, re-parking the rest.** The completion
turn would resume the run with one task's result and the `'skip'` sentinel for
the calls still running. `'skip'` means "executed in an earlier step": the call
is not run and no `ToolReturnPart` is written for it, so the run would send the
provider a response whose tool call has no result, and the task still running
would have nothing left to answer. The results have to arrive together, which
is why the turn waits for the last task.

**A per-task resume channel.** Delivering the result into the suspended call in
place would need the in-flight run to live somewhere durable. The deferred-tool
cycle already parks a run and re-enters it, so a second mechanism beside it
would be two ways to say the same thing.

# What the migration costs

`2026_08_31_0001` flushes every checkpoint again, because the parked call
became a list of calls and the turn gained the answers for all of them.

`2026_08_30_0001` adds `background_tasks.tool_call_id` and flushes every
checkpoint, because the state shape gained the parked durable call and a strict
state does not read an older shape - not only the threads that were
interrupted. On the dev database that meant 17 threads, one of them
interrupted. A flushed thread loses its graph state (the operational spec, the
last build outcome, the verification digest, retrieved memories), any pending
approval, its turn token and cost totals, and a one-agent thread's
`thread_messages_json`; it keeps its conversation row, every chunk in
`conversation_events`, its `messages` rows, its strategy and its
`background_tasks`. The next turn on such a thread reconstructs its spec from
the persisted AST and reads its transcript from the log.
`decisions/no-checkpoint-truncation.md` records the same practice and the
reasoning that settled it.

# What follows

`_resume_graph`, `Command(resume=...)`, `_interrupt_chunks` and the
`interrupt` import are gone; `grep -rn "interrupt(" src/pathfinder` finds no
durable use. PROTOCOL 6.1 holds: the started chunk inside the suspending turn,
progress and completion in the gap, and the continuation as a turn with its own
`start`, `finish` and `done`. PROTOCOL 1.5.3 adds what a step of several tasks
puts in that gap - one started chunk per task, each task's outcome as it
finishes, and one continuation after the last of them - so a client does not
read the first `data-task-completed` as the end of the gap.

A parked call is thread state. `fork_conversation` copies checkpoints
verbatim (`copy_checkpoint_state`), so a branch taken while a durable task
is running would carry a `pending_durable_call` naming tasks whose
completion turn opens on the parent thread only; the branch would hold
calls nothing answers. Not reproduced, and nothing clears or re-parks them
yet.
