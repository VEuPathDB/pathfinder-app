---
type: Decision
title: Every agent belongs to the turn that runs it
description: The module-level Lead agent became a factory the graph is built with, and the three phase sub-agents followed, so each turn and each dispatch constructs its own instance and a per-request model override cannot reach another run; caching one instance behind a factory was rejected because the override is process-wide state.
tags: [assistant-core, ws2, agents, concurrency]
generated: { by: claude-code/opus-5, at: 2026-08-21T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
status: stable
---

# What was found

`lead_agent` was built at import with a hard-coded model id and 14 tools, and
the turn node used it directly. A second assistant could not supply its own
agent, and the per-request model pick was applied with `agent.override(...)`
on that one shared object.

Constructing the agent costs about 50 ms, which is why caching one instance
behind the factory looks attractive.

The three phase sub-agents were the same shape, one level down: `frame_agent`,
`execution_agent` and `verification_agent` were built at import with their
toolsets baked in, and every dispatch overrode the one instance. A toolset that
depends on the user or the turn cannot reach an object that was built before
either existed.

# The decision

`build_lead_agent()` is a factory, the turn node takes it as `build_agent`,
and calls it once per turn. `ai/graph/builder.py` is the single place that
names PathFinder's factory and its pre-turn hook, so the processes that build
a graph cannot drift apart.

`build_frame_agent()`, `build_execution_agent()` and `build_verification_agent()`
are the same for the phases. `BUILD_SUB_AGENT_BY_ROLE` maps a role to its
factory, and the streaming engine calls it once per dispatch.

A cached instance was rejected. The model override is not a per-call argument;
it is state entered on the agent for the duration of the run. One shared
instance means two turns that pick different models race for it, and the
deployment is about to raise worker concurrency above one. Fifty milliseconds
against a turn that calls an LLM is not a cost worth that.

The factory also removed a branch: with a fresh agent, `agent.model` is always
the id the factory baked in, so the check for an already-installed
`FunctionModel` could never fire and is gone.

Each factory names its model as a module constant, and the role-to-model map
reads those constants. A default-model read is a dictionary lookup on an HTTP
request and after every sub-agent tool call, so it never builds an agent to ask
what model that agent would have used.

# Anchor

`apps/api/src/pathfinder/ai/lead/lead_agent.py` holds the Lead's factory,
`ai/graph/builder.py` the wiring, and `ai/agents/frame.py`,
`execution.py` and `verification.py` the phase factories that
`ai/lead/sub_agent_tools.py` maps by role. Done if a module-level `Agent` is
reintroduced, or if `make_lead_node` stops taking its hooks.
