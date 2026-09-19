---
type: Decision
title: The images come from the registry, and cedar pulls
description: A release tag of this repository publishes the api, web, wdk-mcp and research-mcp images to ghcr.io/veupathdb, and the tester host runs quadlet units that name one tag and pull it. Building on cedar, shipping a saved archive over SSH, publishing on every push to main and podman auto-update were rejected.
tags: [deployment, cedar, ci, docker, podman, quadlets, registry]
generated: { by: claude-code/opus-5, at: 2026-09-18T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-18T00:00:00Z }
status: stable
---

# What was decided

PathFinder reaches internal testers on `cedar.penn.apidb.org` as rootless podman
containers that pull images a CI job published. Nothing is built on the host.

`.github/workflows/publish-images.yml` runs on a `v*` tag of this repository and
publishes four images, each tagged with the release and with `sha-<short sha>`,
on `linux/amd64`:

| Image | Built from |
| --- | --- |
| `ghcr.io/veupathdb/pathfinder-api` | `apps/api/Dockerfile`; the worker runs the same image with a command of its own |
| `ghcr.io/veupathdb/pathfinder-web` | `apps/web/Dockerfile` at its `runner` target, with `NEXT_PUBLIC_API_URL` baked as the api's container name |
| `ghcr.io/veupathdb/pathfinder-wdk-mcp` | the `ai-wdk-mcp` repository at the release `docker-compose.yml` names |
| `ghcr.io/veupathdb/pathfinder-research-mcp` | the same repository and release, at its `research` target |

`latest` is never published. Each unit in `quadlets/` names its image at one tag
placeholder, and `deploy/cedar/install.sh` substitutes the release the operator
names in `PATHFINDER_TAG`. An update is a tag bump: the installer rewrites the
units whose file changed, reloads systemd and restarts them.

The measured host is why. Cedar runs Rocky Linux 9.7 and rootless podman 5.6
with no sudo, and carries no docker, compose, uv or node. A build there would
first need a toolchain nobody may install, on a disk three quarters full and
shared with other people's containers.

# What follows from it

**The two MCP tags must agree with compose.** The api imports `veupathdb_mcp` at
the release `apps/api/pyproject.toml` pins, and the served tools must be that
same release. The workflow reads its build context back out of
`docker-compose.yml` and fails when the two disagree, so a bump of one without
the other does not publish.

**The web image carries the address of the api.** `NEXT_PUBLIC_API_URL` is read
on the server only and is baked at `yarn build`, so the image is built with
`http://pathfinder-api:8000`, the container name on the podman network. The
browser calls the web origin and `next.config.ts` rewrites. The same image
therefore serves the SSH tunnel and the tester vhost, and a runtime
`Environment=` for that variable is inert and was removed.

**A published port is a decision, not a default.** Ports 3000 and 8000 on cedar
belong to another user. The web unit publishes `127.0.0.1:3010:3000` and the api
`127.0.0.1:8010:8000`; the two MCP servers, the metasearch and the database
publish nothing and are reached by container name. `node scripts/check-quadlets.mjs`
holds every one of those facts, because podman's own generator runs on Linux and
most of this repository's work happens elsewhere.

**The secrets stay on the host.** The api, the worker, the two tool servers and the
metasearch read `%h/.config/pathfinder/.env`, which the operator writes from
`deploy/cedar/env.example`. That file carries names and one-line meanings, never
a value.

# What would falsify this

A pre-release tag whose four images pull by digest on the host, and a stack that
answers the smoke test in `deploy/cedar/README.md`: `/health/ready` reporting
every subsystem ready with at least one catalog loaded, a sign-in against a
VEuPathDB site, one chat turn on a real provider, and one durable task that
reaches a result.

# What was rejected

**Building on cedar.** It needs a source checkout, a toolchain that cannot be
installed without sudo, and multi-gigabyte builds on a disk shared with other
people's containers. It also makes the running deployment depend on what is
checked out on the box rather than on a release.

**Saving the images and copying them over SSH.** It works once and is a manual
multi-gigabyte step on every release, with no record of what is running.

**Publishing on every push to `main`.** The tester URL would then serve an
untested tree. A tag is the statement that a tree is meant to be run.

**`podman auto-update`.** A push to the registry would restart the tester stack
without anybody saying so, in the middle of a tester's session. An update is a
deliberate tag bump.
