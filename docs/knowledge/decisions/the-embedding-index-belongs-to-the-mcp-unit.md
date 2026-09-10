---
type: Decision
title: The embedding index belongs to the MCP unit, not to the assistant runtime
description: No module inside assistant_core imports the record manager, so record_manager.py and the two tables embedding_vectors / embedding_index_entries moved to veupathdb-mcp: src/veupathdb_mcp/embeddings/ on a declarative base of their own, and the MCP unit ships its own copy of the embedder. Making veupathdb-mcp depend on assistant-core for a pgvector table was rejected.
tags: [embeddings, split, architecture, packaging, persistence, mcp]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: stable
---

# What was decided

`assistant_core/embeddings/record_manager.py` and the two table declarations it
reads are the `veupathdb-mcp` unit's, and they now live in
`apps/api/src/veupathdb-mcp: src/veupathdb_mcp/embeddings/`, which is that unit's
in-repo territory.

**The measurement that decided it.** No module under
`assistant-platform: packages/assistant-core/src/assistant_core/` imported the record manager. Its
consumers were `veupathdb_mcp/embeddings/{semantic_index,study_index}.py`,
`veupathdb_mcp/catalog/{discovery,public_strategy_search}.py`,
`services/eda/catalog.py` and `jobs/tasks.py` - four in the MCP unit, two in the
application. What `assistant_core` itself reads from `embeddings/` is only
`embedder.py`, which owns no table: `memory/{embedding,store,lifespan}.py` call
`get_embedder` and `EMBEDDING_DIMENSIONS`, and the memory store's own vectors
live in LangGraph's `store_vectors`, not in these two tables.

**Two declarative bases, because these two tables reference nothing.** The
runtime's `Base` is shared with the application because foreign keys cross in
both directions; see [the runtime is a
package](the-runtime-is-a-package.md). `embedding_vectors` and
`embedding_index_entries` carry no foreign key at all, so nothing is lost by
mapping them on `EmbeddingBase` in
`veupathdb_mcp/embeddings/tables.py`. Alembic's `target_metadata` is a list of
both metadatas, and the test tree runs `create_all` on both.

**The embedder is copied, not shared.** `assistant_core/embeddings/embedder.py`
keeps the protocol, `get_embedder`, `EMBEDDING_DIMENSIONS`,
`EmbeddingUnavailableError`, and the OpenAI and fake backends, because the
memory store uses them. The MCP unit has its own copy of all of it under
`veupathdb_mcp/embeddings/`. It is the duplication [the runtime is a
package](the-runtime-is-a-package.md) already accepted for `RuntimeSettings`:
about 230 lines against a distribution edge. There is no re-export and no alias;
each unit's consumers import their own unit's module. The copy and the values it
pins are recorded in the platform bundle
(`assistant-platform: docs/knowledge/decisions/the-embedder-is-copied-and-a-host-gates-the-drift.md`).
This application installs both distributions, so it carries the drift gate:
`apps/api/src/pathfinder/tests/unit/platform/test_embedder_copies_agree.py`
compares the three module pairs and the width both alembic chains build.

**Settings and sessions come from the host.** `EmbeddingSettings` in
`veupathdb_mcp/embeddings/settings.py` carries `DATABASE_URL`, `OPENAI_API_KEY`
and the five `EMBEDDING_*` variables under their existing names, with the
`use_embedding_settings_source` / `get_embedding_settings` pattern batches 1 and
2 used; `pathfinder.platform.config.Settings` subclasses it and installs itself.
`veupathdb_mcp/embeddings/db.py` is the same shape for sessions: the index opens
one through `embedding_session()`, PathFinder's API and worker install
`assistant_core.platform.db.async_session_factory` so the index shares their
pool, and a process that installs nothing builds its own engine from
`DATABASE_URL`. That is what the MCP server does today and will do after the
split.

`RuntimeSettings.embedding_input_char_limit` stays, because
`assistant_core/embeddings/openai_embedder.py` still reads it.

**The migration stays PathFinder's.**
`alembic/versions/2026_08_29_0001_add_embedding_record_manager.py` writes frozen
DDL and imports no model, so it needed no rewrite. PathFinder's alembic still
creates both tables for this deployment; the MCP unit's own alembic directory is
a later batch's, when the folder exists.

**The embedder copy carries one member the runtime's does not.** The index has a Postgres
store and the memory store's embedder does not, so `veupathdb_mcp/embeddings/errors.py` declares
`SemanticIndexUnavailableError` and this copy's `EmbeddingUnavailableError` extends it. That is the
whole divergence from `assistant_core/embeddings/embedder.py`; the message, the fields and the
raising site are identical.

**A catalog load does not wait on the index, and does not die with it.** The
catalog is searches, parameters, record types and the site's organism list, and
it comes from WDK and the snapshot on disk. `SearchCatalog._collect_semantic_index`
holds the entries and starts `_sync_semantic_index` beside the load through the
same task spawner the background refresh uses; the load returns without awaiting
it, and a refusal is logged once with the driver's error class. Every session the
index opens goes through one boundary in `record_manager`, which turns a driver
refusal into `IndexStoreUnavailableError`; that and `EmbeddingUnavailableError`
share `SemanticIndexUnavailableError`, so a caller that ranks reads one type and
never a bare `asyncpg` exception. `veupathdb-mcp: tests/unit/gene_lookup/test_catalog_without_the_index.py`
holds it: with the sync enabled and a store that refuses this process,
`list_organisms` still answers with the site's organisms.

# Why

`veupathdb-mcp` reads the semantic index to rank searches, studies and public
strategies. Leaving the record manager in the assistant platform makes the MCP
server depend on `assistant-core`, and through it on `pydantic-ai`,
`langgraph`, `langgraph-checkpoint` and `langgraph-checkpoint-postgres` - the
whole turn runtime - to read a pgvector table. The direction is also wrong: the
assistant platform has to ship without any VEuPathDB deployment, and a table
only a VEuPathDB server reads is not the platform's.

# What was rejected

**`veupathdb-mcp` depends on `assistant-core` for the record manager.** One line
of pyproject and zero code movement, and it drags four agent-framework
distributions into an MCP server that runs no agent. It also leaves the
assistant platform declaring a table no assistant reads.

**One shared embeddings distribution both units depend on.** A fifth package for
230 lines, with its own lock, CI lane and release cadence. The same alternative
was rejected for `CamelModel` in [the client library owns its
foundation](the-client-library-owns-its-foundation.md), for the same reason:
the coordination cost is larger than the duplication.

**The index builds its own engine everywhere.** Simpler than a session source,
and it opens a second connection pool in the API and in the worker against the
same database. The source keeps one pool where a host has one, and still lets a
standalone MCP process stand alone.

# What would falsify this

`grep -rn record_manager assistant-platform: packages/assistant-core/src` returns nothing.
`veupathdb-mcp: tests/unit/test_package_boundary.py` fails if any module of the
distribution, or the served entrypoint's closure, imports `assistant_core` at
all; it carries no allowance.
`cd assistant-platform: packages/assistant-core && uv run pytest tests/unit` fails if the runtime
starts needing the two tables back.
`veupathdb-mcp: tests/unit/gene_lookup/test_catalog_without_the_index.py` fails if a
catalog load starts awaiting the sync again, or if a store refusal reaches the
caller untranslated.

The same split drained the client library's and the MCP server's outbound edges;
see [the client library owns its
foundation](the-client-library-owns-its-foundation.md) and [the MCP server
writes no PathFinder table](the-mcp-server-writes-no-pathfinder-table.md). What
the index itself does is [embeddings are an API call and a record
manager](embeddings-are-an-api-and-a-record-manager.md).
