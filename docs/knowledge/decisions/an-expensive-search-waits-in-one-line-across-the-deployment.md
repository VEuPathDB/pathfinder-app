---
type: Decision
title: An expensive search waits in one line across the deployment
description: A High Speed SNP search, or a search this process marked slow, holds the tool server's Postgres advisory lock per site for as long as its request runs, so the api, the worker and the served tool server send one of them to a site at a time; a turn, a durable body and a served tool call each send one search per site at a time; a wait says "Waiting for <site>" on the turn or on the task. A per-process line, a refusal at the limit and Redis were rejected.
tags: [wdk, load, searches, postgres]
generated: { by: claude-code/opus-5.5, at: 2026-10-09T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-09T00:00:00Z }
status: stable
---

# What was decided

`veupathdb-py` puts every request that runs a search through three lines: the line of
its turn on its site, a gate the host installs, and the site's per-process slots
(`veupathdb-py: docs/knowledge/decisions/a-search-waits-in-line-and-the-host-owns-the-gate.md`).
The gate that spans processes is the tool server's
(`veupathdb-mcp: docs/knowledge/decisions/an-expensive-search-holds-one-line-on-the-database.md`),
and every process installs the same one, so every process takes the same lock.

**The turn.** `run_turn` runs every turn (a message, a completion turn, the chat
debugger) under `services/search_waits.researcher_search_turn`, a client `search_turn`;
`WdkJobContext.restore` runs every durable body under one; the served tool server runs
each tool call under one. Other researchers' turns are not slowed by it.

**The deployment line.** The api and the worker call
`veupathdb_mcp.search_line.install_search_line(database_url, runs_on_the_deployment_line)`
at startup. A request whose searches include one of `HIGH_SPEED_SNP_SEARCHES`, or one
`slow_searches` marked slow on that site, holds the lock `wdk-expensive-search:<site>` for
as long as its request runs, on a connection of its own, so it holds no connection of
the application's pool. The served tool server installs it on the database its index
uses. The most line connections a process opens is one per site with an expensive search
in flight or queued.

**Order.** Postgres grants the lock to its waiters in the order they asked (measured in
the tool server's integration suite), and each process queues its own requests first come
first served, so a process with many waiters does not overtake another process's waiter.

**A reading's budget starts at the send.** Each reading of a bind has
`MEASUREMENT_BUDGET_SECONDS` once its report is sent (`count_search_answer` hands the
budget to the client), so a bind whose readings wait for each other in the turn's line
measures the same readings as one that does not. A turn cannot wait forever: every
request ahead of it in either line is bounded by the client's timeout and is not sent
again.

**What the researcher sees.** A turn that waits five seconds writes a
`data-turn-status` part, "Waiting for <site name>" (the site list's `name`, such as
PlasmoDB), and an empty one when the search starts; the status line shows the notice in
place of the phase name while it stands. A durable body writes the same words on its own
task progress, at the percent it last reported, and its last message again when the search
starts. `pathfinder_wdk_search_wait_seconds{site,kind}` counts every wait by line
(`turn`, `site`, `expensive`), with a site outside the loaded list counted as `other`.

# What was rejected

- **A per-process line only.** The api, the worker and the worker's concurrent turns
  each have their own; a per-process line bounds each process and not the site.
- **A refusal at the limit.** A researcher would see an error for load another
  researcher caused. A wait costs time and nothing else.
- **Redis.** Postgres is the only broker this deployment runs; an advisory lock is what
  the database already offers.
- **A PathFinder copy of the line.** The served tool server is a process of the same
  deployment and cannot import PathFinder; one implementation in the tool server keeps
  the lock name and its behaviour the same in every process.
