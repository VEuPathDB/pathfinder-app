---
type: Decision
title: A run's prompt only grows
description: Within one agent run each request extends the one before it, so the provider's prompt cache reuses it; state sections are held for the run and changes follow the call that made them, every tool stays listed and a rule says which the model may call. A live spend meter, a digest per request, re-rendered state sections, a tool list cut by state and a static set_criterion schema were rejected.
tags: [models, caching, cost, instructions]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: stable
---

# What was decided

A run's instructions name its ceilings, not what it has spent
(`ai/agents/_instructions.pinned_run_budget`), so they read the same for every
request of the run. The runtime digests old tool results in whole blocks
(`assistant_core/conversation/history/elision.py`, `ELIDE_BLOCK`), so the requests
between two blocks extend each other exactly.

Every dynamic section the Lead, FRAME, VERIFY and recovery agents pin goes
through `assistant_core.capabilities.stable_instructions.StableInstructions`: a
run reads each section as the run found it, and a section a tool call changed
follows that call's result as a system note, under `SECTION_UPDATE_LEAD`. A note
in the user's voice read as a new message: the Lead classified the turn again
after each one. Every tool stays on
every request: `assistant_core.capabilities.allowed_tools.AllowedTools` sends the
tools no rule withholds as OpenAI's `allowed_tools`, and refuses a withheld tool
called anyway. The Lead's rule is `intent_gate.withhold_by_turn_state`, and its
pinned "Tools you cannot call now" names what the rule withholds; the
sub-agents' rule is the scratchpad's `withhold_scratchpad_tools`. The sweep's
step id is checked in `sweep_can_run` rather than narrowed in its schema.
`set_criterion` keeps its schema keyed by the open sheets.

# Why

OpenAI's GPT-5.6 models write one cache breakpoint at the end of each request and
reuse a cached prefix only at a message boundary whose whole prefix is unchanged,
tools and instructions first. A write costs 1.25 times the input rate and a read
0.1 times. On the 19 benchmark conversations the Lead read 32,402 cached tokens of
4,786,022 and VERIFY none of 1,652,005, because every request changed its spend
line and digested one more earlier result: the input cost $2.37, more than the
$1.94 it costs with no cache at all. Without those two changes the same requests
cost about $1.59.

# What was rejected

- **A spend meter that moves on every request.** The model can count its own
  calls, the token ceiling is not the one that binds, and a line that changes
  before the history leaves no request a prefix to reuse.
- **Digesting one more result on every request.** It rewrites an earlier message
  each time. A block bounds the whole results kept to the recent pairs plus one
  block.
- **State sections re-rendered on every request.** The Lead's intent, spec and
  ledger and FRAME's workspace, sheets and notes changed in the middle of a run,
  so the instructions before the history changed with them.
- **A tool list cut by the turn's state.** Tools come first in a request, so a
  gate that removed them rewrote every request after a classification.
- **A static `set_criterion` schema with refusals.** It saves FRAME the misses a
  new sheet causes, and gives up the schema that keeps FRAME to the sheet's
  parameter names ([build retries](build-retry-must-be-actionable.md)).
