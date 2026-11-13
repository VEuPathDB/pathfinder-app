---
type: Backlog
title: The identifiers take the Strategist name
description: The screen says VEuPathDB Strategist; the package, stored ids, env variables, wire names, storage keys, URL path and deployment names still say pathfinder. Move each with what reads it, so no saved conversation, worker, client or setting breaks.
tags: [rename, release, deploy, persistence, frontend]
generated: { by: claude-code/opus-5.5, at: 2026-11-13T00:00:00Z }
status: proposed
---

# The identifiers take the Strategist name

The [naming decision](../decisions/the-product-is-named-veupathdb-strategist.md) changed every
string a researcher reads. Each identifier below breaks something if it changes alone.

## In this repository, with a migration

1. **The Python package** `pathfinder` to `strategist`, with every import, `pyproject.toml`
   section (import-linter, vulture, coverage, ruff), the uvicorn command, alembic and the
   scripts. Saved checkpoints hold module paths, so a migration rewrites them in
   `checkpoints`, `checkpoint_blobs` and `checkpoint_writes`, tested on a copy of a dev
   database dump before it runs anywhere.
2. **`assistant_id` and `application_id`** to `strategist`, with a data migration of every
   table that holds them.
3. **`@pathfinder/shared`** and the TypeScript names (`PathFinderLogo`, `PathFinderMark`,
   `PathfinderObserver`), and the brand file names.
4. **Browser storage keys**: read the old key once and write the new one, so no setting
   resets.
5. **`__pathfinder_internal__:`**: cleanup matches both prefixes until no account holds the
   old one.
6. **`X-PathFinder-Service-Token`**: accept both headers for one release, tell each service
   client, then drop the old one.
7. **The README screenshot** (`assets/pathfinder.png`) shows an old screen with the old name;
   take a new one from the running app.

## With the estate, on the same day

8. **The worker command** in `webservices-quadlets` (`python -m pathfinder.jobs.worker`) and
   the `PATHFINDER_*` variables the env files set. A pull request there, merged by the
   systems team, lands with the release that renames the package. Dev runs `:latest` and QA a
   pinned tag, so the dev and QA quadlets name the module through a per-stage variable for
   the release between.
9. **The URL path** `/pathfinder` to `/strategist`: `BASE_PATH` here, the route and
   controller in web-monorepo (`PathfinderController`, `pathfinderUrl`), and a
   `set_strategist_proxy` in the sites' `Containers.pm`, which the systems team owns.
10. **The User-Agent**: tell VEuPathDB operations before `PathFinder/` becomes `Strategist/`.

## Owned by others, optional

11. Image names (`veupathdb/pathfinder-api`, `pathfinder-web`), tagger keys, the Jenkins
    job, the repository name, the database name and the `pathfinder_*` metrics. No researcher
    sees them; rename only with their owners.
