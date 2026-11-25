---
type: Decision
title: A turn reads the strategy once between writes
description: A researcher's turn opens veupathdb-py's turn_reads, so the site client sends a strategy read and a step report once until the turn writes or reads fresh, and a search context read once for the turn; the commit's reconcile read and the release of an abandoned mint read fresh. A timed strategy cache, a copy kept by each caller and a holder on the session were rejected.
tags: [wdk, load, strategy, turn]
generated: { by: claude-code/opus-5.5, at: 2026-11-25T00:00:00Z }
status: stable
---

# Decided

`services/search_waits.py::researcher_search_turn` opens `turn_reads()` beside the turn's
search line. Inside it the site client is the one owner of the turn's copy
(veupathdb-py `decisions/a-turn-reads-once-and-a-definition-is-kept-for-a-time.md`):

- a strategy read and a step's standard report are sent once, and a write to the account
  forgets them, so the next read is what the write made;
- a search's context read, its refreshed parameters and its report are sent once for each
  set of values.

Every other caller (live counts, site counts, the step size, the gene set reads, the
verification) reads through the client and keeps no copy of its own.

Two reads come before a write and read fresh: the commit's `reconcile_sync_state_with_wdk`,
so an edit made on the website or in the panel (which reaches the api process, not the
worker) is planned against, and `delete_released_mint`, so a strategy the researcher saved
during the turn is not deleted.

A durable job, an audit run and an HTTP request open no `turn_reads`, so each of their reads
is sent. The site client keeps search definitions and record types for fifteen minutes in
every one of them.

# Rejected

- **A timed strategy cache.** An edit on the website changes the strategy at any moment.
- **A copy kept by each caller.** About ten callers read the strategy; each would need its
  own rule for when a write makes its copy stale.
- **A holder on the strategy session.** The tool server's reads and the client's own
  read-back after `update_strategy` do not pass through the session.
