---
type: Backlog
title: The checkpointer is set up before the warm-up writes
description: On a fresh database the api fails its startup when the checkpointer's concurrent index builds wait on the warm-up's index sync past the 30-second setup deadline, and a cancelled build can leave an invalid index.
tags: [startup, checkpointer, database, e2e]
generated: { by: claude-code/opus-5.5, at: 2026-11-23T00:00:00Z }
status: proposed
---

# The checkpointer is set up before the warm-up writes

## What happens

The e2e stack on cedar, a fresh database and a warm catalog cache, at dabcf53b1 with
veupathdb-py 0.9.0b14 and veupathdb-mcp 0.9.0b19. `main.py` spawns `_warm_up_subsystems`
before `lifespan_checkpointer` runs `AsyncPostgresSaver.setup()`. The warm-up synced the
embedding index from 15:43:23 to 15:43:43; the setup began at about 15:43:17 and failed at
15:43:47 with `CheckpointTimeoutError: The checkpointer did not answer setup within 30.0
seconds.`, and uvicorn exited. LangGraph's setup runs `CREATE INDEX CONCURRENTLY`, which
waits for every open transaction to end. On two later starts Postgres logged
`canceling statement due to user request` for `checkpoints_thread_id_idx` and then
`checkpoint_blobs_thread_id_idx`; each restart got one index further, and the api came up
on the fourth start. A cancelled concurrent build leaves an invalid index that
`IF NOT EXISTS` then skips, so the table can stay without a usable index.

## Done when

On a fresh database the checkpointer's setup finishes before any warm-up write starts,
an integration test starts the app on an empty database with the index sync on and reads
three valid thread-id indexes from `pg_index`, and the e2e stack starts on its first try.
