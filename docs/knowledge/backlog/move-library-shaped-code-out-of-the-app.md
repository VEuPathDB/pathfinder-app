---
type: Backlog
title: Move library-shaped code out of the app
description: A placement sweep across the four repositories found modules in pathfinder-app that name no gene, strategy or phase and belong to assistant-core, veupathdb-py or veupathdb-mcp, duplications between repositories, and places where a library names PathFinder; the ranked list and its evidence are here so each move can be taken as its own change.
tags: [architecture, layering, assistant-core, veupathdb-py, veupathdb-mcp, assistant-client]
generated: { by: claude-code/fable-5.1, at: 2026-09-08T00:00:00Z }
verified: { by: claude-code/fable-5.1, at: 2026-09-08T00:00:00Z }
status: open
---

# What is wrong

The ownership rule in `CLAUDE.md` says runtime code goes to `assistant-core`,
WDK and EDA reads go to `veupathdb-py` and `veupathdb-mcp`, and only code that
names a gene, a strategy, a WDK search or a phase role stays here. A sweep on
2026-09-08 measured the app against that rule. The six layering contracts hold
and no library imports `pathfinder`, but the split is incomplete in three ways.

## Code in the app that a library should own

Ranked by value over effort. Line counts are `wc -l` at the time of the sweep.

| # | what | files | to | effort |
|---|---|---|---|---|
| A3 | the durable-task subsystem | `ai/tools/durable.py` (210), `jobs/completion_turn.py` (256), `jobs/progress.py`, `jobs/runner.py`, `jobs/registry.py`, the `background_tasks` and `task_progress` models and repositories (1846 total) | `assistant_core` | L |
| A4 | the agent scratchpad | `ai/scratchpad/` (tools, toolset, rendering, compactor) and `persistence/repositories/scratchpad.py` (1189 total) | `assistant_core` | M/L |
| A5 | conversation ownership and turn cancellation | `services/conversations/authz.py` (145), `services/conversations/cancellation.py` (126) | `assistant_core` | M |
| A6 | per-user cost quota | `services/quota.py` (135), `ai/pricing.py` (58), the `monthly_usage` table | `assistant_core` | M |

The evidence for A3 and A4 sits inside the library: `assistant_core/persistence/models.py`
declares foreign keys to `background_tasks.id` and `users.id`, two tables it does not
own, and ships `tests/_host_schema.py` to fabricate them; it also builds the
`background_task_started`, `task_progress` and `scratchpad_updated` chunks for
capabilities the app implements. The runtime records that it takes the two task
tables in
`assistant-platform: docs/knowledge/decisions/the-runtime-owns-its-task-tables.md`,
so A3 is a move to execute, not a question to settle.

## Duplications between repositories

- The settings-source scaffold is written four times, `CamelModel` twice,
  `setup_logging` twice, the testcontainers bootstrap twice.

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

Each move above is taken as its own change with its library release, or recorded as a
decision not to take it. The full measured report is the sweep's record; this card is
its map.
