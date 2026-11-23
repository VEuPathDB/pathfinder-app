---
type: Decision
title: A tool past its retry ceiling is answered, not removed
description: ToolResilience keeps every tool definition offered and answers the call at the retry ceiling with the outage directive, so a VEuPathDB outage costs a tool call instead of the turn. Removing the definition from the offered set, and letting the ceiling raise one more ModelRetry, were rejected.
tags: [agents, resilience, tools, outage]
generated: { by: claude-code/opus-5, at: 2026-09-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-10T00:00:00Z }
status: stable
---

# What was decided

**The offered toolset never shrinks.** `ToolResilience` carries no
`prepare_tools` filter, so a tool the model has already decided to call is
still in the list pydantic-ai resolves the name against.

**The ceiling answers the call.** In `on_tool_execute_error`, a transient
error on a tool that has already failed transiently `circuit_break_threshold`
times in the pass (`ServiceOutageMemory.record_tool_failure`) returns
`_outage_directive` as the tool result instead of raising `TransientRetry`. The model reads "temporary VEuPathDB outage,
not a bad call", prefers a different search, or tells the user the search is
unavailable right now. The directive names the search when the call carries
one and the tool itself when it does not.

**The threshold and the tool's retry budget are the same number.** The
agents are built with `retries=3` and `DEFAULT_CIRCUIT_BREAK_THRESHOLD` is 3:
three transient failures raise `TransientRetry` and spend the three retries,
and the fourth is answered with the directive, on exactly the call whose retry
the run would refuse. The breaker counts transient failures only. A refusal is
charged to the refusal ledger and answered with `CallRefused`, which spends
none of the tool's retries (`platform/refusals.py::KeyedRefusalToolset`). An argument the schema
refuses is charged the same way (`ChargedArgumentRefusals`), so no shape error spends a retry.

# What was rejected

**Removing the definition at the ceiling.** A tool the model has already
chosen resolves against the filtered list, so pydantic-ai raises
`Unknown tool name`, and the retry counter is already at its maximum, so
`_check_max_retries` converts that into `UnexpectedModelBehavior` and the turn
ends in a chat-visible error. Measured during a 14.5 minute DNS failure inside
the compose network: two turns crashed this way, one of them after 240.322 s
of work, and the criterion, its bound organism and its structure were
discarded. The outage directive the module already builds never ran.

**Letting the ceiling raise one more ModelRetry.** Keeping the definition and
changing nothing else moves the same crash one step later: the tool runs, WDK
fails again, and the retry that follows is the one over the budget.

**Counting the outage per search only.** `ServiceOutageMemory` gives up on a
search after two failures, which covers a repeated call on one search. A
blackout fails a different search on each call, so no search reaches two while
the tool passes its own ceiling. Both bounds are needed.
