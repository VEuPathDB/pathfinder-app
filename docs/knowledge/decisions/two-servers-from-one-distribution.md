---
type: Decision
title: The research tools are served by a second server of the wdk-mcp distribution
description: Literature and web search left the app for veupathdb-research-mcp, a second served process of the veupathdb-mcp distribution on port 8110 with its own credentials and its own stream-part namespace. A new repository for the research server, and one mixed server serving both tool groups, were rejected.
tags: [mcp, research, deployment, tool-sources, architecture]
generated: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-09T00:00:00Z }
status: stable
---

# What was decided

The literature and web search clients no longer live in this application. They
are served over MCP by **`veupathdb-research-mcp`**, a second entry point of the
`veupathdb-mcp` distribution (`python -m veupathdb_mcp.research`), on port 8110.
One repository, one lock, one image repository with two build targets: `wdk`
serves seventeen WDK tools on 8100 and `research` serves `web_search` and
`literature_search` on 8110.

PathFinder consumes them the way it consumes every served tool: an
`AdmissionRecord` with `source_id` `veupathdb-research-mcp`, part namespace
`research` and a 60 second budget (`platform/tool_sources.py`), and a
`ToolSourceDeclaration` named `research` on the assistant
(`assistants/pathfinder_spec.py`). The runtime prefixes a source's tools with
the declaration's name, so the model calls `research_web_search` and
`research_literature_search`.

The declaration is not `required`. A deployment that configures no endpoint or
no credential admits nothing, the turn runs without those two tools, and the
Lead answers from the catalog and the strategy state instead. That is what mock
mode is: `PATHFINDER_RESEARCH_MCP_TOKEN` is unset, so the e2e stack needs no
fixture server and no mock-only branch in the spec.

# What was rejected

**A new repository for the research server.** It would have cost a fifth
settings-source scaffold, a second service-token module, a second logging
setup, a second Dockerfile, a second CI workflow, a second lock, a second
release ceremony, and a second `veupathdb-py` pin to keep in step with the
first. Two entry points of one distribution buy the same deployment separation
for none of that.

**One mixed server serving both tool groups.** The WDK server's site guard
validates a site argument on every call, so site-less tools would have needed an
exempt-tool set inside the guard. The WDK process would open connections to
seven open-web APIs, which is a different threat model from reading a WDK
account. `veupathdb-wdk-mcp` would stop describing what it serves. Two
declarations would point at one endpoint. And both tool groups would share one
stream-part namespace, so the research part could not be `data-research.sources`.

# The cost that was accepted

The two servers share one `pyproject.toml`, so the research image installs
`openai`, `pgvector`, `asyncpg`, `alembic`, `numpy` and `sqlalchemy` that no
research module imports. That is image size and audit surface, not runtime
surface: the WDK process still opens no connection to a literature API, because
the research tools run in a different process behind a different credential set.
If the size becomes a problem the next move is optional dependency groups with
the two Dockerfile targets syncing different extras, not a new repository.
