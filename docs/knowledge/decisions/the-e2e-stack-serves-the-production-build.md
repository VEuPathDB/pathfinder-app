---
type: Decision
title: The e2e stack serves the production build, and the dev stack keeps next dev
description: The e2e overlay builds the web container's `runner` target, so port 3000 serves the standalone production server the way CI already did. A dev server compiles a route on every first request and keeps the result, which is what grew the container's heap to 7.44 GiB and had the kernel kill it mid-suite, and it paints two overlays over controls the suite clicks. Bounding the dev server with mem_limit and --max-old-space-size was rejected.
tags: [e2e, playwright, docker, next, gates]
generated: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
status: stable
---

# What was decided

`docker-compose.e2e.yml` pins `web.build.target: runner`. Layered after
`docker-compose.dev.yml` it overrides that file's `target: dev`, so the local
recipe and the CI recipe (which never layered the dev overlay) build the same
image: `next build` with `output: "standalone"`, served by
`node apps/web/server.js`.

The dev stack is unchanged. `docker compose --env-file .env.dev up` still
builds the `dev` target and still runs plain `next dev`, which
[the Turbopack decision](the-dev-server-runs-turbopack.md) settled.

# What was measured

The same container, on the same tree, under the two targets:

| reading | `dev` target | `runner` target |
|---|---|---|
| process | `next dev` | `next-server (v16.2.0)` |
| `NODE_ENV` | `development` | `production` |
| cgroup `anon` at boot | 28 MiB | 96 MiB |
| cgroup `anon` mid-suite | 6.9 GiB | 182 MiB |
| `<nextjs-portal>` in the served HTML | present | absent |
| `.tsqd-parent-container` in the DOM | present | absent |

The dev target's growth is what the kernel acted on. A full-suite run under it
ended `54 failed / 1 skipped / 66 passed` with `OOMKilled=true`, 47 of the
failures being `net::ERR_CONNECTION_REFUSED` after the container died. Rebuilt
on the dev target once more to compare the two, it did not survive the global
setup's twelve route requests:

```
docker inspect pathfinder-web-1 --format '... oom={{.State.OOMKilled}} ...'
exited exit=0 oom=true started=2026-08-31T02:11:38Z finished=2026-08-31T02:14:26Z
```

Two minutes and forty-eight seconds, with the per-route compiles in its own
log reading 14.8 s, 15.2 s, 16.9 s, 21.7 s and 23.4 s. The `runner` target
serves the same routes with no compile at all and finishes the 158 tests in
one process.

The two overlays are gone rather than moved. Next mounts its error-overlay
portal only in a development server. `@tanstack/react-query-devtools` 5.95.2
resolves its own entry to `function () { return null; }` whenever
`process.env.NODE_ENV !== "development"`, so a production build renders no
toggle at all and needs no wrapper of ours.

# What was rejected

**Bounding the dev server** with `mem_limit` on the `web` service plus
`NODE_OPTIONS=--max-old-space-size`. It converts a silent degradation into a
loud crash, which is an improvement, but the suite still cannot finish in one
process, the run still costs a per-route compile inside a spec's budget, and
neither overlay goes away: the seven specs that time out on a click that never
lands stay red. It also keeps the local stack building an image CI never
builds, which is the drift that produced this.

**Forcing the clicks** (`{ force: true }` on the two intercepted buttons). The
buttons really are unreachable for a person on a dev deployment, so a forced
click would assert a reachability the app does not have.

# What follows

A spec that depends on dev-server behaviour has nothing to run against. None
did: the suite's only dev-server dependency was the global setup's route
warm-up, which still earns its place because the production server loads a
route's module graph and renders it cold on the first request.

The switch also shows the product what its users see. One spec changed
verdict: `durable-progress-live.spec.ts:137` passes on a dev server and fails
on the production build, on a duplicate task card a researcher on a real
deployment would read too. That was a defect the dev server was hiding, fixed
in the client's resumed read
(a decision (`assistant-platform: docs/knowledge/decisions/a-resumed-stream-reads-one-turn.md`)), not a reason to serve
`next dev`.

`apps/web/e2e/feature/no-dev-overlays.spec.ts` pins the result: no
`nextjs-portal`, no `[data-nextjs-dev-overlay]`, no `.tsqd-parent-container`,
and the nav rail's Settings button opens the dialog on the first click.

# The stack's capacity, measured

The whole suite (167 tests, 54 files) ran with `--fully-parallel` forced from
the command line on one `ubuntu-latest` runner (4 vCPU, 16 GB), one cell per
worker concurrency (c), worker container count (x) and Playwright worker count
(w). `unexpected` is a test that failed after its retries, `flaky` one that
passed on a retry.

| cell | Playwright minutes | unexpected | flaky | worker CPU peak | api CPU peak |
|---|---|---|---|---|---|
| c8 x1 w2 | 16.9 | 0 | 0 | 89 % | 55 % |
| c4 x1 w2 | 17.9 | 0 | 2 | 87 % | 103 % |
| c4 x2 w2 | 20.0 | 0 | 1 | 99 % | 101 % |
| c8 x1 w4 | 19.4 | 4 | 11 | 88 % | 99 % |
| c4 x1 w4 | 23.8 | 0 | 20 | 96 % | 98 % |
| c4 x2 w4 | 25.3 | 0 | 9 | 94 % | 101 % |
| c8 x1 w8 | 29.9 | 21 | 42 | 91 % | 101 % |
| c4 x1 w8 | 29.5 | 31 | 36 | 69 % | 100 % |
| c4 x2 w8 | 30.9 | 29 | 39 | 99 % | 101 % |

What the table settles:

- **Two Playwright workers per runner.** Every cell at four or eight workers
  fails or flakes, on every stack shape, and is slower: the api process holds
  one full core in every cell, so the runner is the ceiling, not the worker's
  job slots. A second worker container adds nothing at two workers.
- **Worker concurrency 8, one container.** The one cell with no failure and no
  flake, and the fastest. The e2e overlay sets it.
- **Serialization was not the fix.** The turn-driving projects ran in parallel
  here with no failure at two workers, so `fullyParallel: false` is removed and
  the speed comes from shards across runners, each at two workers.

