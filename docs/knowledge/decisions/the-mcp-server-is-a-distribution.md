---
type: Decision
title: The MCP server is a distribution, and PathFinder is one of its consumers
description: pathfinder/{mcp, services/catalog, services/wdk, services/gene_lookup, services/control_*, services/tool_payloads, integrations/embeddings} moved out of apps/api into veupathdb-mcp/ with its own pyproject, lock, tests, README, alembic chain, Dockerfile and CI lane; PathFinder consumes it in process as an editable path dependency and import-linter contract 7 was deleted. Keeping the server inside apps/api, and making PathFinder an MCP client of the served process now, were both rejected.
tags: [veupathdb-mcp, split, architecture, packaging, import-linter, mcp, embeddings, alembic]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: stable
---

# What was decided

The WDK catalog, parameter and gene tools with their MCP transport are
`veupathdb-mcp/`: its own `pyproject.toml`, its own lock file, a
`src/veupathdb_mcp` layout importable with no `pathfinder.` prefix, its own test
tree with a hermetic lane, a pgvector integration lane and a live lane, its own
README, its own alembic chain, its own image and its own CI lane. This is the
shape [the runtime is a package](the-runtime-is-a-package.md) and
[the client library is a distribution](the-client-library-is-a-distribution.md)
already argued for, applied to the third unit.

The mapping is a prefix rename and nothing else, except that the two tool
modules lose the underscore that made them private to a package they no longer
share:

| was | is |
| --- | --- |
| `pathfinder.mcp` | `veupathdb_mcp` |
| `pathfinder.mcp._catalog_tools`, `._user_tools` | `veupathdb_mcp.tools.catalog_tools`, `.user_tools` |
| `pathfinder.services.catalog` | `veupathdb_mcp.catalog` |
| `pathfinder.services.wdk` | `veupathdb_mcp.wdk` |
| `pathfinder.services.gene_lookup` | `veupathdb_mcp.gene_lookup` |
| `pathfinder.services.control_{tests,helpers,types}` | `veupathdb_mcp.controls.control_{tests,helpers,types}` |
| `pathfinder.services.tool_payloads` | `veupathdb_mcp.tool_payloads` |
| `pathfinder.integrations.embeddings` | `veupathdb_mcp.embeddings` |

`pathfinder/integrations/` held nothing else and is gone, with the contract
terms that named it.

# PathFinder consumes it as a library, not as a served endpoint

`apps/api/pyproject.toml` names `veupathdb-mcp` in `[project].dependencies` with
a `[tool.uv.sources]` path row. PathFinder's agent tools call the catalog, WDK
and gene-lookup functions **in process**: measured, 132 production import edges
from `pathfinder` into the unit, in the toolsets, the transport routers, the
durable jobs and the experiment engine.

**The rejected alternative is making PathFinder an MCP client of the served
process**, which `assistants/site_help` already is through its declared
`wdk-mcp` source. It is the cleaner end state - one deployment, one credential
path, one place a tool is defined - and those 132 edges are its cost: every one
becomes a served call with a wire schema, a bearer and a timeout, and the agent
tools that wrap them in typed results would have to parse them back. In-process
use is the first cut; the served path stays available because the same functions
serve both adapters.

# The semantic index and its two tables move with it

`embedding_vectors` and `embedding_index_entries` are read and written by this
unit alone; [the embedding index belongs to the MCP
unit](the-embedding-index-belongs-to-the-mcp-unit.md) settled that. The
migration that creates them moved into this distribution's own alembic chain,
recorded in `alembic_version_veupathdb_mcp`, so two chains share one database
and neither sees the other's history. PathFinder's chain is re-linked across the
gap; it has not shipped, so no stub revision was left behind.

The chain ships **inside** the package (`src/veupathdb_mcp/alembic/`) with the
ini at the folder root. A chain beside the ini is not in the wheel, and after
publishing PathFinder pins a version rather than a path: a distribution that
owns tables must be able to create them wherever it is installed.
`python -m veupathdb_mcp.migrate` is a separate entrypoint and the server does
not migrate at start, because a replica that only reads must not change a
schema. In the compose stack PathFinder's startup runs both chains, which is
what created these tables before.

# What the boundary is, and how it is proved

`veupathdb_mcp.**` reaches no `pathfinder`, `assistant_core`, `pydantic_ai`,
`langgraph` or `fastapi`. `tests/unit/test_package_boundary.py` walks every
module and asserts it, and the served entrypoint's own closure is asserted the
same way. The proof is not the test but the environment it runs in:
`cd veupathdb-mcp && rm -rf .venv && uv sync --frozen && uv run pytest tests/unit`
resolves a lock that names no application, so a `pathfinder` import fails to
resolve rather than failing a lint rule. Import-linter contract 7 ("the MCP
server never imports the agents or the API transport") is deleted, because the
package's dependency list says it.

**The rejected alternative is keeping the server inside `apps/api` behind those
contracts.** It costs nothing to keep and it is what the tree did until now. It
was rejected because the owner is publishing the folder as its own repository,
and because the served image inherited 1.95 GB of PathFinder - the PIGuard ONNX
model, the agent framework and the whole application tree - to serve seventeen
WDK reads.

# What stayed behind, and why

- The served integration lane (`apps/api/.../tests/integration/mcp/`) drives the
  deployed container through `pydantic_ai.mcp.MCPToolset`, the client the
  assistant uses, and needs a registered account and an owned strategy step. The
  MCP package's own served gate is the `mcp_conformance` command.
- Tests that span the two distributions: the catalog tests that also drive an
  agent tool, the EDA-spec guard that authors its input with PathFinder's
  service, and the settings-and-tables wiring in
  `tests/unit/platform/test_mcp_distribution_wiring.py`.
- `pathfinder.platform.config.Settings` keeps subclassing `McpSettings` and
  `EmbeddingSettings`, so one settings instance still serves the process and the
  environment variable names are unchanged.

# Publishing

Delete the `veupathdb-mcp` row from `apps/api/pyproject.toml`'s
`[tool.uv.sources]`, pin `"veupathdb-mcp>=0.1.0"`, and drop the three
`COPY veupathdb-mcp ...` lines from `apps/api/Dockerfile` and the sibling copy
from `veupathdb-mcp/Dockerfile`, whose context then becomes the folder itself.
