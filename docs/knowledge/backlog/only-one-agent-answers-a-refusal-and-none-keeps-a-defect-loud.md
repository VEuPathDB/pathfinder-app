---
type: Backlog
---

# Only one agent answers a refusal, and no sub-agent keeps a defect loud

**What I did.** Read the capability list of every agent this deployment runs:
`ai/lead/lead_agent.py:180`, `ai/agents/frame.py:202`, `ai/agents/execution.py:205`,
`ai/agents/verification.py:214`, `assistants/site_help/agent.py`.

**What I got.** `ServiceRefusalRetry` is on the Lead and on nothing else. The
three sub-agents carry `ToolResilience` instead, whose `on_tool_execute_error`
routes an `AppError` through `classify_error` to `SEMANTIC`
(`ai/capabilities/error_classification.py:51`) and returns a directive string.
The `site_help` agent declares no `capabilities=` at all, so a tool of that
assistant that raises an `AppError` propagates and ends the turn. In the other
direction, `ToolResilience`'s UNKNOWN branch
(`ai/capabilities/resilience.py:368-381`) logs `Unknown tool error` and returns
an `INTERNAL_TOOL_ERROR` directive, so a `TypeError` or a `KeyError` inside a
sub-agent tool becomes a tool result the model reads and works around.

**Why that's wrong.** Two opposite failures, one per side. A `site_help` user
meets "Response failed" for a refusal the Lead's user does not, which is the
incident this deployment already fixed once. And a real defect on FRAME, BUILD
or VERIFY never reaches the error path or the alert: the run continues, the
model narrates around the broken tool, and the researcher gets a plausible
answer built without it.

**Why it happens.** Two capabilities were added at different times for
different reasons and no rule says which agent carries which.
`ToolResilience` predates the refusal seam and answers every category,
including UNKNOWN; `ServiceRefusalRetry` answers only what the model can
correct. Nothing holds the pair complete over the agent registry.

**Fix.** State one rule and hold it with a test over every agent factory: each
agent carries the refusal seam, and `ToolResilience`'s UNKNOWN branch re-raises
instead of returning a directive, so a defect ends the run wherever it happens.
The `site_help` agent gets the seam with the rest.

**What you'd get.** A refusal answers the model on every assistant, and a defect
ends the run on every agent, so an alert fires where today a directive hides it.
