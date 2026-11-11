---
type: Decision
title: An open tab is told of a new web build
description: The web image names its build by a hash of the web's sources (PATHFINDER_WEB_BUILD, set in the Dockerfile), serves it at GET /api/v1/web-build and sets it as Next's deploymentId; an open tab compares it with the build it loaded every five minutes and on focus, and shows a banner with a Reload button when they differ. Reloading on its own, comparing with the api's version, and a release version as the build name were rejected.
tags: [web, deploy, release]
generated: { by: claude-code/opus-5.5, at: 2026-11-11T00:00:00Z }
status: stable
---

# What was decided

An open tab keeps running the JavaScript it loaded until the page reloads, so a
tab opened before a deployment keeps the old code. The web image now names its
build: the builder stage of `apps/web/Dockerfile` sets `PATHFINDER_WEB_BUILD` to
the first 12 characters of a hash over the web's sources, the shared types, the
spec and the lockfile, for `yarn build` only. `next.config.ts` inlines it with
`env` and sets it as `deploymentId`. A build without it (`next dev`, a local
`yarn build`) names no build and checks nothing.

`GET /api/v1/web-build` (`app/api/v1/web-build/route.ts`) answers the build the
server runs, with `Cache-Control: no-store`. `NewReleaseBanner`, inside
`SystemReadyGate`, reads it every five minutes and when the tab regains focus
(`lib/api/webBuild.ts`). When the served build differs from the tab's own
(`lib/webBuild.ts::aNewerBuildIsServed`), the banner says "PathFinder has been
updated." with a Reload button.

The tab reads its build as `process.env.PATHFINDER_WEB_BUILD`, with a dot.
Next inlines only that form, so an index access would leave the client with no
build and the banner silent; `typings/process-env.d.ts` types the property so the
dotted form passes the index-signature rule.

`deploymentId` also turns on Next's own version-skew handling: a client-side
navigation after a deployment becomes a full page load.

# Rejected

**Reloading on its own.** Threads are durable on the server, but a reload drops
an unsent draft and an open card's local choices. The banner leaves the moment
to the researcher.

**Comparing with the api's version.** The api and web containers restart a
minute or so apart, and between releases the dev estate rebuilds `:latest` with
no version change. The web's own build, served by the web, has neither gap.

**A release version as the build name.** The same version names every `:latest`
build on the dev estate, so a push to main would not be seen. A hash of the
sources changes with every change that reaches the bundle.
