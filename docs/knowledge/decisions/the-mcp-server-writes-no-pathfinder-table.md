---
type: Decision
title: The MCP server writes no PathFinder table, so a second deployment can run it
description: The two paths from the served veupathdb-wdk-mcp entrypoint to pathfinder.persistence were an identity lookup whose result was only stringified and an export write a second deployment cannot perform; both are cut, the gene_sets package __init__ that dragged 1009 LOC of store into the closure is empty, and the server's own foundation lives under pathfinder/mcp/. An ExportSink protocol and a read-only connection were rejected.
tags: [mcp, split, architecture, packaging, persistence, auth]
generated: { by: claude-code/opus-5, at: 2026-09-04T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-04T00:00:00Z }
status: stable
---

# What was decided

The module set that becomes the `veupathdb-mcp` distribution - what is now
`veupathdb_mcp/{tools,catalog,wdk,gene_lookup,controls,embeddings}/**`,
`veupathdb_mcp/tool_payloads.py` and the server's own modules -
imports nothing from `pathfinder.platform`, `pathfinder.persistence`,
`pathfinder.ai`, `pathfinder.transport`, `pathfinder.jobs`, or the half of
`pathfinder.services` that stays with the application. It reached them 54
times; the count is now 0. The transitive closure of the served entrypoint
`python -m veupathdb_mcp` fell from 162 modules / 17869 LOC to 133 / 15027 and
names no PathFinder table.
`tests/unit/test_veupathdb_mcp_unit_boundary.py` is the gate: it walks the unit,
parses each module, and walks the entrypoint closure over the real import graph.

## The two paths to `pathfinder.persistence`, and what replaced each

**An identity lookup whose result was only stringified.** `veupathdb_mcp/auth.py` called
`services/wdk_identity.py::resolve_veupathdb_bearer`, which mapped a VEuPathDB
token onto a `users` row through `async_session_factory()`, and the resulting
UUID was used at exactly one place: `client_id=str(bearer.user_id)`. The server
now verifies the token's ES512 signature through the client library's own
`validate_oauth_token` and names the caller by the OAuth subject, cached per
token for five minutes in `veupathdb_mcp/identity.py`. `resolve_veupathdb_user_id`, the
`users` write and the session factory stay in the application, which needs the
row because its own resources belong to it.

**An export write a second deployment cannot perform.**
`veupathdb_mcp/tool_payloads.py::attach_control_downloads` wrote PathFinder's
`exports` table so a control outcome carried download links. It moved up to
`services/export/control_downloads.py`, beside the two callers that want the
links: the agent tool and the durable job. The served tool returns the outcome
with `downloads` unset. The same cut splits `services/gene_sets/enrichment.py`:
the stored-set half keeps the export, and the by-value half a tool calls is
`veupathdb_mcp/wdk/enrichment/gene_ids.py`.

## The package `__init__` that cost 1009 LOC of closure

`veupathdb_mcp/tools/user_tools.py` imported `enrichment` from the `services.gene_sets`
package, and `gene_sets/__init__.py` imported `GeneSetService`, which imports
`store.py`, which imports `platform/store.py` and the `gene_sets` table. The
module the tool needed touches no store. `gene_sets/__init__.py` is now empty
and every consumer names the module it wants.

## Where the server's own foundation lives

`pathfinder/mcp/` is the future `veupathdb_mcp` root, so what the server owns
lives there: `locks.py` (from `platform/keyed_locks.py`), `tool_errors.py`
(from `platform/tool_errors.py`, which is the shape an MCP tool returns and
which the agent toolsets import from there), `service_tokens.py` (the
`ServiceTokenRegistry` half of `platform/principal.py`), `settings.py`,
`identity.py`, `logging_setup.py`, and `__version__`. Import-linter contracts 3
("services never import transport or AI"), 6 ("the science never imports an
assistant's composition root") and 7 ("the MCP server never imports the agents
or the API transport") all stay green with services and `ai` importing
`veupathdb_mcp.tool_errors`: none of the three names `veupathdb_mcp` as a
forbidden module.

The catalog machinery takes its process concerns as arguments rather than
reading them: `DiscoveryService(cache_dir=..., budget_bytes=..., policy=...,
spawn=...)` and `preload_all(readiness)`, which the served MCP process calls;
PathFinder's warm-up drives `get_catalog` per site under its own budget instead
([a site that is down is down on its own](a-site-that-is-down-is-down-on-its-own.md)).
The settings come from
`McpSettings` through the same host-installed source the client library uses
([the client library owns its foundation](the-client-library-owns-its-foundation.md)),
and `pathfinder.platform.config.Settings` subclasses it, so one instance still
serves the application's process.

# What was rejected

**An `ExportSink` protocol on `attach_control_downloads`.** It keeps a seam in
the server for something the server never does. The function has one caller
chain, both ends of which are the application, so moving it up deletes the
seam rather than typing it. A protocol would also have to name
`ExportedFile`, which is a PathFinder row.

**Leaving the `users` mapping behind an interface.** The MCP server does not
need an account at all: every tool acts on WDK as the caller's own bearer, and
the only use of the internal id was a string. An interface would preserve a
question the server has no reason to ask.

**A read-only database connection for the whole server.** It would still make
`veupathdb-mcp` depend on PathFinder's schema and migrations. The server keeps
a database only for the semantic index it reads (`embedding_vectors`,
`embedding_index_entries`), which the embedding move takes into the unit.

**Renaming the environment variables.** `VEUPATHDB_OAUTH_URL`,
`PATHFINDER_MCP_BASE_URL`, `PATHFINDER_MCP_SERVICE_TOKENS`,
`SITE_CATALOG_BUDGET_MB`, `CATALOG_REFRESH_ENABLED` and
`EMBEDDING_INDEX_SYNC_ENABLED` keep their names and their meanings, so the
compose file and every deployment read unchanged. A rename is a deployment
decision, not a refactor.

# What would falsify this

An import in the unit-3 module set that names `pathfinder.platform`,
`pathfinder.persistence`, `pathfinder.ai`, `pathfinder.transport`,
`pathfinder.jobs` or a service outside the unit, or an entrypoint closure that
reaches a PathFinder table. The boundary test asserts all of it.

# Related

- [The runtime is a package, so the boundary is an installation fact](the-runtime-is-a-package.md)
- [The client library owns its foundation, so no edge points up out of it](the-client-library-owns-its-foundation.md)
- [The MCP server verifies with the client library's bearer verifier, and publishes RFC 9728](mcp-auth-reuses-the-api-verifier.md)
- [The wdk-mcp server is a product module](the-wdk-mcp-server-is-a-product-module.md)
