---
type: Decision
title: The images come from the estate's pipeline, and the estate's units pull them
description: Jenkins builds the api and web images from this repository's Jenkinsfile with the shared pipelib Builder and pushes them to docker.io/veupathdb, latest from main and the version from a semver tag; the systems team runs them from the estate's service-definitions repository, the api, worker and web of the development stage on latest with podman auto-update, QA and production moved by tagger, and the two MCP servers always at the ai-wdk-mcp release the api pins. The GHCR workflow as the lasting pipeline, rootless units under one account, pinned tags pulled by hand, PEP 440 release tags, MCP servers that follow latest, building on the host and image archives copied over SSH were rejected.
tags: [deployment, cedar, ci, docker, podman, quadlets, registry, jenkins]
generated: { by: claude-code/opus-5.5, at: 2026-10-08T00:00:00Z }
status: stable
---

# What was decided

PathFinder runs the way every VEuPathDB estate service runs: an image pipeline
the estate shares, a registry every estate host already pulls from, and units the
systems team deploys.

**Jenkins builds the images.** The shared `pipelib` `Builder` reads
`Jenkinsfile` and pushes to Docker Hub under `docker.io/veupathdb`:

| Image | Built from |
| --- | --- |
| `pathfinder-api` | `apps/api/Dockerfile`, context the repository root; the worker runs the same image with a command of its own |
| `pathfinder-web` | `apps/web/Dockerfile`, context the repository root, with `NEXT_PUBLIC_API_URL=http://pathfinder-api:8000` |
| `pathfinder-wdk-mcp` | the `ai-wdk-mcp` repository's own `Jenkinsfile`, from its `Dockerfile`, on that repository's own version line |
| `pathfinder-research-mcp` | the same repository and version line, from its `Dockerfile.research` |

A push to `main` publishes `:latest`. A tag publishes its version without the
`v`: `v0.2.0-b5` publishes `:0.2.0-b5`, and a release without a pre-release,
`v1.2.3`, publishes `:1.2.3`, `:1.2` and `:1`. A tag that `pipelib` cannot read as
semver publishes nothing, so a release of this repository is tagged with the
semver spelling of the api version (`v0.2.0-b5` for `0.2.0b5`), which PEP 440
reads as the same version. `pipelib` would also publish a semver tag written
without its `v`; `scripts/check-release.mjs` refuses that and every other form,
and CI runs it on every tag push.

**The systems team runs the stack.** The units live in the estate's
service-definitions repository, `VEuPathDB/webservices-quadlets`, and the systems
team deploys them as it deploys every estate service. They name
`docker.io/veupathdb/pathfinder-<service>` at one of two tags each stage sets:
`PATHFINDER_TAG` for the api, the worker and the web, and `PATHFINDER_MCP_TAG`
for the two MCP servers. The website's own host forwards `/pathfinder` to the
stage's web container, which is what makes PathFinder same-origin with the
website ([PathFinder signs in through the site that hosts it](pathfinder-signs-in-through-the-site-that-hosts-it.md)).
The units and the secrets are not in this repository.

**The development stage follows `main`; QA and production follow tags.** The
development stage runs the api, the worker and the web at `:latest` with
`podman auto-update`, so a merge reaches it without a step. QA and production
name a version, moved by `VEuPathDB/tagger` as the estate promotes every service.

**The MCP servers run the release the api pins, in every stage.** The api
imports `veupathdb_mcp` at the `ai-wdk-mcp` tag `apps/api/pyproject.toml` pins in
`[tool.uv.sources]`, and the tools it serves over the wire must be the same
release. `ai-wdk-mcp` publishes on a version line of its own, so its `:latest`
says nothing about that pin. `PATHFINDER_MCP_TAG` is therefore the pin's tag
without its `v` (`0.2.0-b5` for a pin of `v0.2.0-b5`), never `latest`, and a
release of this repository that moves the pin moves `PATHFINDER_MCP_TAG` in the
estate stack's environment in the same release, as a change in the services
repository. Nothing in this repository can read that repository, so the release
recipe in `CLAUDE.md` names the step. The pin must itself be a semver tag for
that image to exist. `v0.2.0-b4` is the first such release.

**The interim pipeline stays until the cutover.**
`.github/workflows/publish-images.yml` still publishes the four images to
`ghcr.io/veupathdb` on a `v*` tag, and the rootless units in `quadlets/` and
`deploy/cedar/install.sh` still serve the tester host from them. All three are
deleted once the estate stack serves the development site.

# What follows from it

**Each image is the last stage of its Dockerfile.** `pipelib` passes a
Dockerfile and a context and no build target. The web Dockerfile ends on its
`runner` stage, and `ai-wdk-mcp` builds its research server from a file of its
own (`veupathdb-mcp: docs/knowledge/decisions/each-image-is-the-last-stage-of-its-own-dockerfile.md`).

**The build is buildah's.** `pipelib` runs `podman build --format=docker`, so an
image keeps its `HEALTHCHECK`, and a `COPY` whose glob matches nothing fails the
build where BuildKit copies nothing. The api image's optional
`ollama_models.yaml` is copied as `ollama_models.yaml*`, a glob the tracked
example always matches.

**The MCP build contexts in this repository name the pin.** The served tools
must be the release the api runs in process, so `scripts/check-release.mjs` fails, in pre-commit and in CI, when an
`ai-wdk-mcp` build context in `docker-compose.yml` or in the interim workflow
names another release than `apps/api/pyproject.toml`.

**The web image carries the address of the api.** `NEXT_PUBLIC_API_URL` is read
on the server only and is baked at `yarn build`, so the image is built with
`http://pathfinder-api:8000`, the api's name on the stack network, and the
browser calls the web origin, which rewrites. The base path `/pathfinder` is
baked the same way and is the same in every stage, so one web image serves
every stage.

**A service port on a developer machine binds the loopback interface.**
`docker-compose.yml` publishes the api, the web and the two MCP servers on
`127.0.0.1` only, because the development sign-in route answers on the api and
the web. The database port stays on every interface, where host tools reach it
by the machine's own address.

# What would falsify this

A push to `main` that leaves `docker.io/veupathdb/pathfinder-api:latest` and
`pathfinder-web:latest` older than the commit; a tag `v0.2.0-b5` that publishes
no `:0.2.0-b5`; the development stage not answering
`https://<development site host>/pathfinder/` with the new build after an
auto-update; or a stage whose MCP servers report another version on `/health`
than the `veupathdb-mcp` the api has installed.

# What was rejected

**The GHCR workflow as the lasting pipeline.** Estate hosts pull Docker Hub, and
one pipeline builds every estate service. A package a workflow creates on GHCR
is private, and the organization does not allow a public one, so every host
needs a login of its own.

**Rootless units under one account.** The systems team cannot manage units that
run under one person's account, and the host gives that account no sudo.

**Pinned tags pulled by hand on every stage.** The estate promotes by tag through
`tagger`, and a hand step per merge leaves the development stage behind `main`.
The cost of following `main` is accepted: an update restarts the development
stack, and a turn running at that moment ends with the worker's failure message
and can be sent again.

**PEP 440 release tags (`v0.2.0b5`).** `pipelib` reads tags as semver and
publishes nothing for one it cannot read; the pipeline is shared, so the tag
follows it, and `pyproject.toml` keeps its spelling.

**MCP servers that follow `latest` with the rest of the development stage.**
`ai-wdk-mcp`'s `main` moves on its own schedule, so the served tools would run
code the api has not imported and a change to a tool's arguments would reach the
api before the pin does.

**Building on the host.** It needs a source checkout and a toolchain on a host
shared with other services, and it makes the running deployment depend on what
is checked out rather than on a published image.

**Saving the images and copying them over SSH.** A manual multi-gigabyte step on
every release, with no record of what is running.
