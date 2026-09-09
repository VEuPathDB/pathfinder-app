---
type: Decision
title: The wdk-mcp server is a product module of the api, served from the api image
description: veupathdb-wdk-mcp lives at pathfinder/mcp/ inside the api distribution, imports pathfinder.services directly, and gains fastmcp-slim[server] as an api dependency; a standalone package, a mount inside the FastAPI app, and exporting the ai/tools wrappers were rejected. A tool whose realistic duration exceeds the 60-second per-server budget declares its own floor in tool `_meta`.
tags: [mcp, architecture, packaging, wdk, tools]
generated: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
status: superseded
---

> Superseded by [the MCP server is a distribution](the-mcp-server-is-a-distribution.md):
> `pathfinder/mcp/` became the `veupathdb-mcp` distribution, and the contract
> that guarded it became that package's dependency list. What follows is why the
> module came first.

# What was decided

`veupathdb-wdk-mcp` is `pathfinder/mcp/`, a module of the api distribution. It
builds a `FastMCP` server whose tools call `pathfinder.services` and nothing
else, and it runs as its own process on the api image rather than inside the
api process.

Three facts make that the cheapest correct shape:

- **The tools are the services.** Every served tool is a service call with a
  site and its arguments. A separate distribution would have to depend on
  `pathfinder.services`, which is the api.
- **The coupling that matters is enforced, not conventional.** Import-linter
  contract "The MCP server never imports the agents or the API transport"
  forbade `pathfinder.ai` and `pathfinder.transport` from `pathfinder.mcp`, so
  a turn-scoped object could not reach a stateless server by accident. That
  contract is now the `veupathdb-mcp` distribution's dependency list; see
  [the MCP server is a distribution](the-mcp-server-is-a-distribution.md), which
  supersedes this decision's premise while keeping its conclusion.
- **The api environment now carries the server extra.** `fastmcp-slim` arrives
  with `pydantic-ai` in its client extra only, so `import fastmcp.server`
  raised `ImportError` until `fastmcp-slim[server]` joined the api's own
  dependencies.

# What was rejected

**A standalone `veupathdb-wdk-mcp` distribution.** It would either vendor the
retrieval code, which puts a second copy of the WDK rules behind a release
cycle, or depend on `pathfinder-api`, which is the same coupling with an extra
package boundary and no new guarantee. The boundary that earns its keep here is
the import contract, and that already exists.

**Mounting the MCP endpoint inside the api's FastAPI app.** The server holds
per-site catalogs and a semantic index, and those grow with the sites a caller
touches. Inside the api they would grow against the ceiling that chat needs.
Its own process gives the growth a ceiling of its own.

**Exporting the `ai/tools/standalone` wrappers.** They take a `RunContext` and
an `AgentDeps`, and four of them write PathFinder's discovery gate on
`agent_state`. Serving them would export the turn. The retrieval half is the
service; the gate stays in `ai/`.

# The per-tool budget

An admission record carries one `max_call_seconds` for a whole server, and it
defaults to 60. Two served tools cannot fit that: `enrich_gene_ids` runs five
analyses three at a time and each polls WDK to 300 seconds, and
`run_control_tests_on_search` shares the control machinery the durable step
variant estimates at 180 seconds.

Each of those tools therefore declares its own floor in tool `_meta`, under
`org.veupathdb.assistant/maxCallSeconds`, next to the `streamPart` key the same
`_meta` already carries. A consumer that admits this server with a smaller
budget is choosing to time the tool out, and can read the number before it
does. Declaring nothing was rejected: the default would silently cut the call
at 60 seconds and the failure would look like a WDK fault.

The served entrypoint reaches no PathFinder table, which is what a second
deployment needs; see
[the MCP server writes no PathFinder table](the-mcp-server-writes-no-pathfinder-table.md).
