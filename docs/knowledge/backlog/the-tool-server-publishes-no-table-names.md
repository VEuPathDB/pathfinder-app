---
type: Backlog
---

# The tool server publishes no list of the tables it owns

**What I did.** Wrote the autogenerate filter that keeps another distribution's
tables out of this application's chain
(`apps/api/src/pathfinder/platform/migrations.py`) and tried to read every name
from the distribution that owns it.

**What I got.** Three of the four owners answer. The runtime publishes
`assistant_core.migrate.OWNED_TABLES` and `assistant_core.migrate.VERSION_TABLE`.
The tool server publishes its two index tables through
`veupathdb_mcp.embeddings.tables.EmbeddingBase.metadata.tables`, but it names its
version table only at `veupathdb_mcp/alembic/env.py:19`, in a directory with no
`__init__.py`, so nothing can import it. `MCP_VERSION_TABLE =
"alembic_version_veupathdb_mcp"` in `platform/migrations.py` is the retyped copy.

**Why that's wrong.** A retyped name goes stale without a gate. If the tool
server renames its version table, this application's filter admits it and the
next generated revision carries `op.drop_table("alembic_version_veupathdb_mcp")`,
which unstamps the tool server's chain and makes its next upgrade rebuild the
semantic index tables.

**Why it happens.** `veupathdb_mcp.migrate` exports `upgrade_head` and nothing
else; `OWNED_TABLES` and `VERSION_TABLE` have no home in an importable module of
that distribution.

**Fix.** In `VEuPathDB/ai-wdk-mcp`, export `OWNED_TABLES` and `VERSION_TABLE`
from `veupathdb_mcp.migrate` the way `assistant_core.migrate` does, release a
tag, and replace the literal and its `MCP_VERSION_TABLE` constant here with the
imported names. `tests/unit/platform/test_migrations.py` then reads them from
their owner too.

**What you'd get.** Every name in the filter is read from the distribution that
owns it, so a rename in either library fails this application's gate instead of
its next migration.
