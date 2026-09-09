---
type: Decision
title: PathFinder admits veupathdb-wdk-mcp from two settings, and only with both
description: The admitted set is built in code from an endpoint setting and a credential setting, and admits the server only when both are set; the processes that drive turns install it at start. A nested endpoint list in one environment variable, and installing from the assistant registry, were rejected.
tags: [assistants, mcp, admission, configuration, deployment]
generated: { by: claude-code/opus-5, at: 2026-08-25T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-25T00:00:00Z }
status: stable
---

# What was decided

`pathfinder/platform/tool_sources.py` builds this deployment's
`AdmittedSources` in code. The record's shape is fixed there - the source id is
the name the server publishes, the part namespace is `wdk`, the credential mode
is `service`, the budget covers the longest call the server declares - and only
two values come from settings: `PATHFINDER_WDK_MCP_URL`, the endpoint a turn
dials, and `PATHFINDER_WDK_MCP_TOKEN`, the credential presented there. The
server is admitted only when both are set, so a deployment never calls an
admitted endpoint without the credential it takes, and a half-finished
configuration admits nothing rather than failing at the transport.

The same module answers `source_credential`, the runtime's credential provider.
It refuses a source id this deployment holds no credential for, and refuses an
empty token by name.

The processes that drive turns install the set at start: the worker
(`jobs/worker.py`) and the chat debugger (`devtools/chat.py`). The API process
never runs a turn, so it admits nothing and needs nothing.

# What was rejected

**One environment variable carrying the endpoint list.** The admission decision
already rejected `RuntimeSettings` fields for the nested record
(`assistant-platform: docs/knowledge/decisions/admitted-tool-sources-are-installed-by-the-host.md`); the remaining
temptation was a JSON blob in one variable. It was rejected for the same
reason: the fields that make a record safe - the namespace a source may bind
parts in, the approval policy, the call budget - are the deployment's
guarantees, and a guarantee that arrives as a parsed string can be weakened by
an editing mistake nothing rejects. In code they are constants a test pins.

**Installing from the assistant registry.** The composition root builds both
assistants and is reached by every process, so it looked like the one place to
install. It was rejected because `get_assistant_registry` is cached: the
install would fire on whichever call happens to be first, and a test that
installs its own set would have it silently replaced by the next cache miss. An
entry point that installs at start states the order instead of depending on it.

# The consequence, stated

A dev stack that sets no token admits nothing, so site help answers with its
two local tools and the turn is unchanged. Turning the pilot on is two
variables on the api and worker services, plus the same secret in the served
container's `PATHFINDER_MCP_SERVICE_TOKENS`. A second admitted server means a
second record built beside this one, not a new configuration format.

# Anchor

`apps/api/src/pathfinder/platform/tool_sources.py`, pinned by
`tests/unit/platform/test_tool_sources.py`: nothing is admitted without both
settings, the admitted id is the name the server publishes, the budget covers
the server's longest declared call, and an unconfigured credential is refused
by name.
