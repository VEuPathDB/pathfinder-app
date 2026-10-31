---
type: Convention
title: Database connection budget
description: Every process of one deployment fits inside 90 connections on a Postgres that allows 100. The table names each connection source, the setting that sizes it and its worst case, and one test holds the sum.
tags: [database, postgres, connections, operations, testing]
generated: { by: claude-code/opus-5, at: 2026-10-25T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-25T00:00:00Z }
status: stable
---

The estate database runs Postgres with its default `max_connections` of 100, and
the deployment does not raise it. Every process together may open at most 90;
the other 10 are for `superuser_reserved_connections` (3), an admin session and
a migration session (alembic runs on a connection of its own at api start).

Every pool is sized by a setting, and every default fits the budget. A pool keeps
its size open and opens its overflow only in a burst, so an idle deployment
holds few connections. `.env.example` lists each setting.

`pathfinder/platform/connection_budget.py` holds the table below as code.
`tests/unit/platform/test_the_connection_budget_holds.py` sums it from the
setting defaults and holds the sum at 83. It also scans the served modules of
`pathfinder`, `assistant_core` and `veupathdb_mcp` for every call that opens a
connection, counts the calls of each module against `OPENER_CALLS`, and fails
when a module, or a second pool in a listed module, is not in the table.
`tests/integration/persistence/test_a_burst_fits_the_connection_budget.py` runs
15 dispatches, an audit job and a durable job together and holds the peak inside
the budget (35 connections measured on the test database).

| process | source | setting | worst case |
|---|---|---|---|
| api | request pool (`assistant_core.platform.db`) | `DB_POOL_SIZE` 2 + `DB_MAX_OVERFLOW` 10 | 12 |
| api | thread lock pool | `LOCK_POOL_SIZE` 2 + `LOCK_POOL_OVERFLOW` 18 | 20 |
| api | job queue pool (procrastinate) | `JOB_QUEUE_POOL_MAX_SIZE` 4 | 4 |
| api | graph checkpointer, held for the process | none | 1 |
| api | memory store, held for the process | none | 1 |
| api | shared LISTEN connection of every chat stream | none | 1 |
| api | expensive-search line (veupathdb-mcp `install_search_line`) | `SEARCH_LINE_POOL_SIZE` 1 + `SEARCH_LINE_MAX_OVERFLOW` 1 | 2 |
| api | strategy line (veupathdb-mcp `install_strategy_line`) | `STRATEGY_LINE_POOL_SIZE` 1 + `STRATEGY_LINE_MAX_OVERFLOW` 0 | 1 |
| worker | request pool | `DB_POOL_SIZE` + `DB_MAX_OVERFLOW` | 12 |
| worker | job queue pool | `JOB_QUEUE_POOL_MAX_SIZE` | 4 |
| worker | job queue LISTEN, one per procrastinate worker (turns and audits) | none | 2 |
| worker | checkpointer and memory store of each running job | 2 x `WORKER_CONCURRENCY` 4 | 8 |
| worker | audit run and review leases, one per audit job, on a pool of their own | `AUDIT_CONCURRENCY` 2 (at most 4) | 2 |
| worker | heartbeat, one per procrastinate worker | none | 2 |
| worker | expensive-search line | as the api | 2 |
| worker | strategy line | as the api | 1 |
| wdk-mcp | embedding index pool | `EMBEDDING_DB_POOL_SIZE` 2 + `EMBEDDING_DB_MAX_OVERFLOW` 6 | 8 |
| wdk-mcp | expensive-search line | `SEARCH_LINE_POOL_SIZE` + `SEARCH_LINE_MAX_OVERFLOW` | 2 |
| wdk-mcp | strategy line | `STRATEGY_LINE_POOL_SIZE` + `STRATEGY_LINE_MAX_OVERFLOW` | 1 |
| research-mcp, service, searxng | none | none | 0 |
| **total** | | | **86** |

The api and the worker share the request pool with the embedding index
(`use_embedding_session_factory`), and a durable job's reads come from the
worker's request pool. An audit run holds its lease for the whole run, so the
leases have a pool of their own (`services/audit/lease_pool.py`) and the turns
keep the worker's request pool; `AUDIT_CONCURRENCY` 4 makes the total 88. A chat turn, a durable job and a
completion turn each hold at most a checkpointer and a memory store at once,
which is the per-job row. Raising `WORKER_CONCURRENCY` or a pool setting means
recomputing the total: the unit test fails when the defaults leave the budget.

The search line and the embedding pool are veupathdb-mcp's (0.2.0b52 and later),
read from the same environment by every process that installs them. The line
holds its lock as a transaction lock, so a failed, cancelled or lost search
frees it. Its pool has no timeout: a search waits for the line and is never
refused. Two line connections per process means expensive searches on three
sites at once take turns in the process, which is the accepted cost of the cap.
