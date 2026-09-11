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
error on a tool whose `ctx.retries` count has reached
`circuit_break_threshold` returns `_outage_directive` as the tool result
instead of raising `ModelRetry`. The model reads "temporary VEuPathDB outage,
not a bad call", prefers a different search, or tells the user the search is
unavailable right now. The directive names the search when the call carries
one and the tool itself when it does not.

**The threshold and the agent's retry budget are the same number.** The four
agents are built with `retries=3` and `DEFAULT_CIRCUIT_BREAK_THRESHOLD` is 3,
so the directive is returned on exactly the call whose `ModelRetry` the run
would refuse.

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
