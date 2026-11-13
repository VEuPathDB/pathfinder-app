---
type: Backlog
title: The identifiers take the Strategist name
description: The screen and every name this repository alone reads say Strategist; the package, stored ids, two quadlet-set variables, the User-Agent, the URL path and the deployment names still say pathfinder. Each moves with what reads it, so no saved conversation, worker, client or setting breaks.
tags: [rename, release, deploy, persistence, frontend]
generated: { by: claude-code/opus-5.5, at: 2026-11-13T00:00:00Z }
status: proposed
---

# The identifiers take the Strategist name

The [naming decision](../decisions/the-product-is-named-veupathdb-strategist.md) lists what
already moved. What is left, in order:

## 1. The estate starts the worker by its command

A pull request to `VEuPathDB/webservices-quadlets` (merged by the systems team) sets
`Exec=bin/strategist-worker` in `pathfinder-worker@.container`, adds
`STRATEGIST_WDK_MCP_URL` and `STRATEGIST_RESEARCH_MCP_URL` beside the `PATHFINDER_` pair in
`00-pathfinder_defaults.env` and the worker's `Environment=` lines, and renames the commented
service-token target to `STRATEGIST_SERVICE_TOKENS`. It merges only after QA runs 0.9.1a2 or
later, the first image that holds `bin/strategist-worker`.

## 2. The package and the stored ids (after step 1)

- **The Python package** `pathfinder` to `strategist`: every import, the `pyproject.toml`
  sections (import-linter, vulture, coverage, ruff), the uvicorn command, alembic, the scripts
  and `bin/strategist-worker`. Saved checkpoints hold module paths, so a migration rewrites
  them in `checkpoints`, `checkpoint_blobs` and `checkpoint_writes`, tested on a copy of a dev
  database dump first.
- **`assistant_id`** to `strategist`, with a data migration of every table that holds it.
- **The two MCP URL settings** read `STRATEGIST_*`; a later quadlet change drops the
  `PATHFINDER_` pair.
- **The README screenshot** (`assets/pathfinder.png`) shows an old screen with the old name;
  take a new one from the running app.

## 3. With other teams

- **`application_id`**: the systems team rewrites the `pathfinder:` entries of the
  `*_MCP_SERVICE_TOKENS` secrets as `strategist:`, and the app reads the new key the same day.
- **The URL path** `/pathfinder` to `/strategist`: `BASE_PATH` here, the route, controller and
  location message type in web-monorepo, and a `set_strategist_proxy` in the sites'
  `Containers.pm`, owned by the systems team. The old path redirects for one release.
- **The User-Agent** becomes `Strategist/` after VEuPathDB operations is told.
- **Metric and trace names** (`pathfinder_*`, `pathfinder-api`) change after the owners of any
  dashboard or alert are told.
- **Image names, tagger keys, the Jenkins job, the repository, the database and the env-file
  names**: optional; no researcher sees them.
