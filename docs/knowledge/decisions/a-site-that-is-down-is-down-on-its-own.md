---
type: Decision
title: A site that is down is down on its own
description: Readiness is every process subsystem plus at least one loaded catalog, so one dead VEuPathDB site is degraded and not fatal - named in the health body and in GET /api/v1/sites, refused fast on its own routes with a 503 SITE_UNAVAILABLE, retried in the background on an interval, marked in the site selection, read for a WDK identity only while it answers, kept out of every site-less entry point, and left with its own shell so its local saved work stays reachable. Rejected - readiness requires every catalog, and resolving every WDK identity against the configured default site, both of which let a portal outage take the whole deployment down.
tags: [infra, startup, availability, transport, health]
generated: { by: claude-code/opus-5, at: 2026-09-07T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-07T00:00:00Z }
status: stable
---

# The incident

On 2026-09-07 `GET https://veupathdb.org/veupathdb/service/record-types` returned
no HTTP status for 60 s while `plasmodb.org` answered the same call in 0.77 s.
The api preloaded every site's catalog at startup and `/health/ready` answered
503 until all fourteen were loaded, so the portal's load spent its 120 s client
timeout (`sites.yaml routing.portal_timeout`), retried, and never finished. The
readiness body read every subsystem `ready: true`, `catalogs.veupathdb.ready:
false`, `not_ready: ["catalog:veupathdb"]`, at 1.65 GB with no OOM. Compose
declared the api unhealthy after its probe window, its dependents never started,
and the e2e job died before Playwright ran, twice. One VEuPathDB site being down
took PathFinder down for every site.

Measured the same day inside the api container, loading the portal's catalog
into an empty cache directory: the load raised `WDKError` after 375.0 s, the
client's 120 s timeout times its retries. plasmodb's cold load, on the same
process, took 2.6 s.

# What was decided

**Readiness is about this process.** `ReadinessState.all_ready` is every fixed
subsystem ready - database, embedding backend, PIGuard, graph checkpointer - and
`any(c.ready for c in catalogs.values())`. `not_ready` keeps naming the fixed
subsystems, plus the single entry `catalogs` when no catalog is loaded at all, so
a 503 always says which precondition is missing. `degraded` names the sites whose
catalog failed or is still loading, on `/health/ready` and on `/health/system`.

**A preload has a per-site budget.** The warm-up in `main.py` calls
`platform/site_catalogs.py::preload_catalogs`, which registers every site and
loads them with `asyncio.gather`, each inside `asyncio.timeout` of
`SITE_PRELOAD_TIMEOUT_SECONDS` (30 by default). A site that misses its budget or
refuses is `mark_catalog_failed(site, <error class>)` and logged once at warning.
One dead site costs 30 s, not 120 s times the client's retries. The catalog
error is the error class alone, because `GET /api/v1/sites` reports it and a
message can carry a URL or a token.

Measured on 2026-09-07 inside the api container, building into an empty cache
directory: plasmodb 2.6 s, fungidb 3.5 s. A cold build takes seconds, so 30 s
holds one comfortably. The builds themselves are serialized by the
one-build-at-a-time semaphore in `veupathdb_mcp`, so on a fully cold deployment
the last of fourteen sites can spend its budget queued and be marked degraded
even though it answers; the retry then loads it, because a pass runs one site at
a time against a free semaphore. A warm snapshot needs no semaphore, which is the
normal case.

**A degraded site is retried until it answers.** The lifespan spawns
`run_catalog_retry_loop`, which every `SITE_RETRY_INTERVAL_SECONDS` (60 by
default) reloads the degraded sites, one at a time, under the same budget, and
marks a site ready when its load succeeds. The task is cancelled with the
lifespan. A site that is already ready is never reloaded by it.

**One refusal covers both ways a site can be unreachable.**
`SiteUnavailableError` reads "<site> is not responding (<cause>)", where the
cause is the error class or `catalog still loading`. The login route raises it
too: `password_login` posts with no error mapping, so with the portal down
`POST /api/v1/veupathdb/auth/login` raised `httpx.ReadTimeout` out of the route
and answered an opaque 500 after the client's whole read timeout. That route
stays outside the catalog gate, because refusing it would sign the caller out
of every site.

**A degraded site's own routes refuse at once.** One dependency,
`transport/http/deps.py::require_available_site`, resolves the site a request
names - the path parameter on `/api/v1/sites/{siteId}/...`, the `siteId` query
parameter elsewhere - and raises `SiteUnavailableError` (503,
`ErrorCode.SITE_UNAVAILABLE`, detail naming the site and the error class) before
any catalog or WDK call. `POST /api/v1/chat` carries its site in the body, so
`require_available_chat_site` reads the body and raises the same refusal.
`tests/unit/transport/test_site_gate_route_table.py` names every gated route and
every route that reaches a site without the gate, with the reason.

**The site selection warns.** `SiteResponse` carries `available` and
`unavailableReason`, computed from the readiness state at request time. The nav
rail's site menu keeps a degraded site selectable, since the researcher's saved
work is local, and marks it "Not responding"; the trigger carries the same mark
when the current site is degraded. The sites query refetches every 60 s, matching
the retry, so a recovered site clears its mark without a reload.

**A WDK identity is read on a site that answers.** The identity gate turns a
request's token into the internal user by asking a site for `/users/current`,
and `GET /users/current` returns the same WDK user id (`1216062453`,
`isGuest: false`) on plasmodb, on toxodb and on the portal, measured
2026-09-07 with one account: the id is account scoped and no site holds a
privileged answer. So `require_session_matches_wdk_identity` takes the site the
request names - the optional `siteId` on
`transport/http/deps.py::require_registered_wdk_identity`, the body's site on
`POST /api/v1/chat`, the configured default when a request names none - and
`services/wdk_identity.py::identity_site` hands the read to the first loaded
site whenever the named one is degraded. A request that names a degraded site is
refused 503 `SITE_UNAVAILABLE` by that same dependency, before the read.
`fetch_current_user` catches `VEuPathDBError` as well as the `httpx` errors, so a
WDK outage means the token names nobody and the session keeps its own identity,
never a 502. `GET /api/v1/veupathdb/auth/status` reads the same loaded site, so
the app shell does not block on a dead one. Every parameter that carries a site
id spells it `siteId`, on the wire as well as in a path template, which is what
lets one dependency bind it.

**The entry flow never opens a degraded site.** Every site-less route -
`app/page.tsx`, `app/conversation/page.tsx`, `app/workbench/page.tsx` and
`app/workbench/[id]/page.tsx` - is a `force-dynamic` server component calling
`app/entrySiteRedirect.tsx::redirectToEntrySite`, which reads
`GET /api/v1/sites` on the server and redirects to the portal's own URL when it
answers, else the first site in the list's order that answers
(`lib/sites/entrySite.ts::chooseEntrySite`); the workbench item route keeps its
gene-set id in the target. When the request fails or no site answers it renders
the startup screen instead of redirecting, so there is no loop and no endless
spinner. The stored site selection follows the URL the app shell renders, so the
entry flow's choice replaces a stored degraded site and a deep link to a
degraded site leaves the selection alone.

**A degraded site keeps its shell; only its VEuPathDB-backed content is
refused.** `SiteAvailabilityGate` renders inside both app shells
(`app/[siteId]/(app)/layout.tsx` and `app/[siteId]/workbench/layout.tsx`),
around the routed content and below the nav rail, so a URL that names a
degraded site still draws the rail with its site switcher and its "Not
responding" marker, and the conversations list and saved gene sets - this
deployment's own rows, which the api serves for a degraded site - stay
reachable. The notice takes the content area: the site's display name, the
error class, and a link to every site that answers, re-rendered to the app by
the 60 s refetch. The sign-in prompt is the one thing the gate still replaces
outright, because a site that answers nothing cannot authenticate anyone; a
sign-in that was attempted and refused shows the same notice inline, read from
the problem body by `lib/api/errors.ts::siteUnavailableRefusal`.
`app/[siteId]/layout.tsx` gates the subtree on the process being ready and
nothing else.

# What was rejected

**Readiness requires every catalog.** This is the behaviour the incident
measured. A catalog is a cache of one external site, so making all fourteen a
precondition hands every VEuPathDB site a veto over the whole deployment: the
container is unhealthy, its dependents never start, and CI dies before it tests
anything. The earlier decision
[per-site catalogs are evicted under a budget](per-site-catalogs-are-evicted-and-the-warm-up-does-not-block-the-bind.md)
already took `/health/ready` off the compose healthcheck for the same reason;
this finishes the thought inside the endpoint itself.

**Resolving every WDK identity against the configured default site.** This is
what `services/wdk_identity.py` did. Measured 2026-09-07 with a real login on
PlasmoDB while the portal answered nothing: `GET /api/v1/eda/studies?siteId=plasmodb`
answered `502 WDK_ERROR` after 374.41 s, because the identity read went to the
portal and escaped the except tuple as a `WDKError`. Thirty-four routes sit
behind that gate - every gene-set write, every experiment, every EDA read, every
strategy operation - so one dead site refused all of them on every other site.
Threading a site id through `platform/security.py::resolve_principal` was
rejected in turn: it is a dependency of 73 of the 94 routes, so declaring a
`siteId` there would put a meaningless query parameter on all of them.
`resolve_veupathdb_bearer` keeps the configured default and gets its answer from
`identity_site`.

**Letting a request wait for the site.** Without the gate, a call to a dead
site's route waits out the WDK client timeout, 120 s on the portal, and the
researcher reads a spinner instead of a reason. The refusal names the site and
the error class in under a second.

**Dropping a degraded site from `GET /api/v1/sites`.** It reads as "the site does
not exist", and it hides the saved strategies and gene sets the researcher can
still open, which are this deployment's own rows.

**Keeping the per-site retry inside `veupathdb_mcp`.** `DiscoveryService.preload_all`
is the served MCP process's own startup path and its pyproject names no
`pathfinder`. The budget and the retry belong to the caller that owns the
readiness report, so PathFinder's warm-up drives `get_catalog` per site and
leaves the distribution alone.
