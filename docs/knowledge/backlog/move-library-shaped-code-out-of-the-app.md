---
type: Backlog
title: Move library-shaped code out of the app
description: A placement sweep across the four repositories moved every module in pathfinder-app that names no gene, strategy or phase into assistant-core, veupathdb-py or veupathdb-mcp; what is left is duplication between repositories and one library that still names PathFinder.
tags: [architecture, layering, assistant-core, veupathdb-py, veupathdb-mcp, assistant-client]
generated: { by: claude-code/fable-5.1, at: 2026-09-08T00:00:00Z }
verified: { by: claude-code/fable-5.1, at: 2026-09-08T00:00:00Z }
status: open
---

# What is wrong

The ownership rule in `CLAUDE.md` says runtime code goes to `assistant-core`,
WDK and EDA reads go to `veupathdb-py` and `veupathdb-mcp`, and only code that
names a gene, a strategy, a WDK search or a phase role stays here. A sweep on
2026-09-08 measured the app against that rule. Every module the sweep ranked
has moved; what is left is duplication between repositories and one library
that still names PathFinder.

## Duplications between repositories

- `CamelModel` is written twice: `assistant_core.platform.pydantic_base` and
  `veupathdb.model`. The testcontainers bootstrap is written three times, in
  each repository's own conftest. The settings-source scaffold and
  `setup_logging` are settled the other way, as decisions to write them per
  distribution (`assistant-platform: docs/knowledge/decisions/the-settings-source-scaffold-is-written-per-distribution.md`
  and `.../the-process-logging-setup-is-written-per-distribution.md`).

## Library code that names PathFinder

- `veupathdb/domain/strategy/` is PathFinder's authoring model inside the client
  (already its own backlog item).

## Enforcement

The sixth import-linter contract, "The application imports no private module of an
installed distribution", is in `apps/api/pyproject.toml`. It names each library's
private modules one by one, because a forbidden contract matches whole module segments
and cannot name a submodule of an external package; the three libraries are therefore
`root_packages` beside `pathfinder`. One `ignore_imports` remains, for a test that
needs a name a library does not yet publish, and it is deleted by the release that
publishes it. A stale exception fails the gate.

What the contract does not close is the other half: `veupathdb_mcp` declares almost no
public surface, and the app imports sixty of its modules.

# Done when

Each duplication above is deduplicated with its library release, or recorded as a
decision not to take it. The full measured report is the sweep's record; this card is
its map.
