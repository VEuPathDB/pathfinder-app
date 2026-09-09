---
type: Decision
title: A declared tool source reaches a one-agent assistant through its deps
description: site_help carries the turn's resolved toolsets on its own TurnContext subclass into its own deps model, and its agent names them with a run-context toolset function that pydantic-ai wraps in a DynamicToolset. Widening the runtime's agent factory to take toolsets, and carrying them in a context variable, were both rejected.
tags: [assistants, mcp, site-help, pydantic-ai, toolsets]
generated: { by: claude-code/opus-5, at: 2026-08-25T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-25T00:00:00Z }
status: stable
---

# What was decided

The turn's driver resolves an assistant's declarations before the turn context
exists and hands the ready toolsets to the assistant as
`TurnContextRequest.tool_sources`
(`assistant-platform: docs/knowledge/decisions/a-tool-source-session-belongs-to-the-turn.md`). Site help receives them on
`SiteHelpTurnContext`, a frozen subclass of the runtime's `TurnContext`, and
`build_deps` folds them into one `CombinedToolset` on `SiteHelpDeps`. The agent
declares `toolsets=[turn_tool_sources]`, a function of the run context that
answers with `ctx.deps.tool_sources`.

`pydantic_ai.Agent` accepts a toolset OR a function of the run context and
wraps the function in a `DynamicToolset`
(`pydantic_ai/agent/__init__.py:487-494`, `toolsets/_dynamic.py:20-38`), which
re-reads it per run step and enters and exits what it returns
(`_dynamic.py:75-118`). Because `build_deps` builds the combined toolset once
per agent run, the object identity is stable across the run's steps and the
session is entered once. The transport is reference counted, so the entry the
turn's driver already holds keeps the session open across the run's own entry
and exit (`pydantic_ai/mcp.py:1165-1268`).

A turn that resolved nothing puts `None` on the deps and the function answers
`None`, which is the toolset-free agent site help was before it declared
anything.

# What was rejected

**Widening the runtime's agent factory.** `TurnAgentFactory` is
`Callable[[], AgentT]` and `single_agent_graph` calls it with no arguments, so
the obvious move is to pass the resolved toolsets as an argument. It was
rejected because the graph is compiled before the turn's sources resolve
(`jobs/impls/chat_turn_impl.py` builds the graph, then `run_turn` opens the
sessions), so the factory has nothing to receive at the only moment it is
built. Threading the value would mean re-ordering the runtime's turn seam for
one assistant, and every other assistant would pay the widened signature.

**A context variable.** The turn's driver could set the toolsets on a context
variable that the factory reads. It was rejected because the assistant already
has a typed per-turn channel, and a second, invisible one makes the agent's
tools depend on a value no signature names.

# The consequence, stated

An assistant that wants a declared source subclasses the turn context it is
given and names the toolset in its own deps; the runtime keeps one shape for
every assistant, and the zero-source path is byte-for-byte what it was. A
toolset that must not be re-entered per run step must be built once per run,
which is why `build_deps` and not the toolset function does the combining.

# Anchor

`apps/api/src/pathfinder/assistants/site_help/spec.py` and `agent.py`, pinned
by `tests/unit/assistants/site_help/test_spec.py` (the sources reach the deps,
and an empty turn hands the agent nothing) and `test_mock.py` (a tool the
turn's source serves is the one the agent calls).
