---
type: Backlog
title: The identifiers take the Strategist name
description: The screen, every name this repository alone reads, the package and the assistant id say Strategist, and the package waits for the estate to start the worker by its command; the application id, two quadlet-set variables, the User-Agent, the URL path and the deployment names still say pathfinder. Each moves with what reads it, so no saved conversation, worker, client or setting breaks.
tags: [rename, release, deploy, persistence, frontend]
generated: { by: claude-code/opus-5.5, at: 2026-11-13T00:00:00Z }
status: proposed
---

# The identifiers take the Strategist name

The [naming decision](../decisions/the-product-is-named-veupathdb-strategist.md) lists what
already moved. What is left, in order:

## 1. The estate starts the worker by its command

VEuPathDB/webservices-quadlets#42 (merged by the systems team) sets
`Exec=bin/strategist-worker` in `pathfinder-worker@.container`, adds
`STRATEGIST_WDK_MCP_URL` and `STRATEGIST_RESEARCH_MCP_URL` beside the `PATHFINDER_` pair in
`00-pathfinder_defaults.env` and the worker's `Environment=` lines, and renames the commented
service-token target to `STRATEGIST_SERVICE_TOKENS`. It merges only after QA runs 0.9.1a2 or
later, the first image that holds `bin/strategist-worker`.

The package `strategist` and the assistant id `"strategist"` are done here and wait for this
step: the image they ship in starts no worker from a quadlet that names
`-m pathfinder.jobs.worker`. Release them only after the estate runs `bin/strategist-worker`.
The same day, the client library's four citations of the renamed `wdk/strategist/` and
`eda/strategist-integration-concept.md` paths are updated in `VEuPathDB/ai-veupathdb-client`.

## 2. After step 1

- **The old assistant id on a request**: `AssistantId` (`platform/identity.py`) still reads
  `"pathfinder"` on a chat request body as `"strategist"`, for a browser tab opened before the
  release. Remove it in the release after.
- **The two MCP URL settings** read `STRATEGIST_*`; a later quadlet change drops the
  `PATHFINDER_` pair.
- **The README screenshot** (`assets/pathfinder.png`) shows an old screen with the old name;
  take a new one from the running app.

## 3. With other teams

- **`application_id`**: the systems team rewrites the `pathfinder:` entries of the
  `*_MCP_SERVICE_TOKENS` secrets as `strategist:`, and the app reads the new key the same day.
- **The page address** `/app/pathfinder` to `/app/strategist`: VEuPathDB/web-monorepo#1946
  moves the route and redirects the old one. Once the sites run it, this repository's links to
  the site page (`strategist_page_url`, share links) name `/app/strategist`. The app's own
  base path `/pathfinder` is the iframe's source, which no researcher reads; it stays.
- **The User-Agent** becomes `Strategist/` after VEuPathDB operations is told.
- **Metric and trace names** (`pathfinder_*`, `pathfinder-api`) change after the owners of any
  dashboard or alert are told.
- **Image names, tagger keys, the Jenkins job, the repository, the database and the env-file
  names**: optional; no researcher sees them.
