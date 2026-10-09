---
type: Decision
title: PathFinder signs in through the site that hosts it
description: PathFinder is served at /pathfinder on a VEuPathDB website's own host, reads a researcher's WDK identity only from that website's Authorization cookie, never writes or deletes that cookie outside local development, and honors its own pathfinder-auth session only while the cookie names the same account; signing in and out is the website's. A PathFinder password form, a host of its own, a base path per environment and a session honored on its own cookie were rejected.
tags: [security, auth, veupathdb, wdk, deployment, frontend]
generated: { by: claude-code/opus-5.5, at: 2026-10-08T00:00:00Z }
status: stable
---

# What was decided

PathFinder is served at the fixed base path `/pathfinder` on the host of the
VEuPathDB website that shows it, and a page of that website embeds it under the
website's own header. Every environment uses the same base path, local
development included (`apps/api/src/pathfinder/platform/config.py::BASE_PATH`,
`basePath` in `apps/web/next.config.ts`), so one web image serves every host.

**The website's login cookie is the only credential for a WDK account.** WDK
sets `Authorization` at `Path=/` and names no domain:
[`SessionService.getAuthCookie`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/SessionService.java#L313-L318)
calls `cookie.setPath("/")`, at the WDK sha
`veupathdb-py: docs/knowledge/wdk/sources.md` pins, and the login response's
cookie takes FgpUtil `CookieBuilder`'s default path `/` and a null domain
([`CookieBuilder`](https://github.com/VEuPathDB/FgpUtil/blob/a63e80460f6ffe3bec2144a9a42d74e0f92d584c/Web/src/main/java/org/gusdb/fgputil/web/CookieBuilder.java#L10),
[`toJaxRsCookie`](https://github.com/VEuPathDB/FgpUtil/blob/a63e80460f6ffe3bec2144a9a42d74e0f92d584c/Web/src/main/java/org/gusdb/fgputil/web/CookieBuilder.java#L51-L62)).
The cookie is therefore host-only: a page under `/pathfinder` on the website's
host receives it with every request, and a page on any other host never does.
The request middleware in `main.py` puts it on
`veupathdb_auth_token_ctx`, as it does a token sent in a header. PathFinder
never writes or deletes that cookie. The one exception is
`GET /api/v1/dev/site-login`, which mounts only when `API_ENV` is `development`
and `WDK_DEV_EMAIL` and `WDK_DEV_PASSWORD` are both set
(`Settings.offers_dev_site_login`): it signs in with the development account through
`veupathdb.wdk.password_login` and sets the cookie as the website would, so
local development has a website login to follow.

**PathFinder's session follows the website login.** `pathfinder-auth`
(HttpOnly, SameSite=Lax, `Path=/pathfinder`, Secure outside development) names
the internal user that owns the conversations, memories, keys and spend. A
request that carries it is served only while the website login is a registered
token for that same user: `platform/security.py::site_login_user` verifies the
token locally and maps its account to the internal user, and
`resolve_principal` refuses a request with no website login (401
`WDK_LOGIN_REQUIRED`) or with one for another account (401
`WDK_IDENTITY_MISMATCH`). `POST /api/v1/veupathdb/auth/refresh` mints the
session from the website cookie and relinks it when the account changed;
`GET /api/v1/veupathdb/auth/status` answers `signedIn` alone and clears
`pathfinder-auth` when the website login is gone. A bearer token and a
dev-login session carry their own identity and are served on it.

**Signing in and out is the website's.** PathFinder has no password form, no
logout route and no account name of its own to show. `GET /health/config`
reports the deployment's site, `PATHFINDER_SITE` (default `veupathdb`; startup
refuses a site the sites file does not list), and `siteSignInUrl`, that site's
`/app/user/login`, or the development route when that route is mounted. A
signed-out PathFinder shows one notice
(`apps/web/src/app/components/SignedOutNotice.tsx`) whose link opens that page
in the whole window, with the page the researcher was on as its `destination`.
A logout in the website header leaves no registered token in the cookie, so
the next PathFinder request is refused and the notice returns.

**One layout, inside the website's page.** The web app has no top bar and no
embedded variant. The rail carries the logo at the top and the spending meter at
the bottom (`AppNavRail.tsx`, `RailLogo.tsx`, `RailQuotaMeter.tsx` under
`apps/web/src/app/components/`). When the parent window has the same origin, a
route change posts `{ type: "pathfinder:location", path }` to it
(`apps/web/src/lib/frameBridge.ts`), so the website page keeps its address bar
on the PathFinder page.

**A link PathFinder writes for later is a path under `/pathfinder`.** An export
download link and the development sign-in address carry no host, so the browser
resolves them on the website that serves PathFinder and no setting names it.

# What would falsify this

- `apps/api/src/pathfinder/tests/unit/platform/test_session_follows_site_login.py`
  serves a session with no website login, or one whose login names another user.
- `apps/api/src/pathfinder/tests/unit/transport/test_auth_cookies.py` finds a
  route other than the development sign-in that writes `Authorization`, or a
  `pathfinder-auth` cookie outside `Path=/pathfinder`.
- `apps/api/src/pathfinder/tests/unit/transport/test_dev_login_is_test_only.py`
  finds `/api/v1/dev/site-login` on the production app, or on a development app
  without the development account.
- `apps/api/src/pathfinder/tests/unit/transport/test_health_config_site.py`
  reads a sign-in address that is not the deployment site's login page.

# What was rejected

**Keeping PathFinder's password login.** Two writers of one cookie name on one
host: PathFinder's sign-in overwrites the website's `Authorization`, and a
PathFinder logout signs the researcher out of the website too.

**A host of its own.** The website's cookie is host-only, so it never reaches
another host, and PathFinder would need a second sign-in.

**A base path per environment.** Next fixes the base path when it builds, so
each environment would need its own web image.

**Honoring `pathfinder-auth` on its own for its 24 hours.** A logout on the
website would leave PathFinder signed in as the account that left.

**Keeping an embedded layout beside the plain one.** PathFinder is shown in one
context, the website's page, and a page opened on its own is the same page
without the frame around it. A second layout is a second shell that every
feature has to be tested in, with no context that needs it.

**PathFinder's own bar imitating the website's header, or its bar under the
website's.** A copy of the header drifts from the real one, and its sign-in and
sign-out would be PathFinder's again. Two stacked bars take height from the
conversation and the canvas and show the account in two places.

**Local development by a pasted token or by the mock model alone.** A pasted
token is a three-year credential copied by hand into each browser, and the mock
model reaches no WDK account, so neither runs the sign-in a deployment runs.
The development route sets the same cookie the website sets, so local
development exercises the deployed path.

**Reading the frame's address when it loads.** A navigation inside PathFinder
fires no load event, so the website's address bar would stop following.

**Deriving the deployment's site from the request's host.** No deployment
serves several hosts, and `GET /health/config` is the one place that changes if
one does.

**Building a download link from the request's `Origin`.** It loses
`/pathfinder`, and a link the worker builds has no request to read.
