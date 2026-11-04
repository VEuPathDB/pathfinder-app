---
type: Decision
title: The site comes from the website that frames PathFinder
description: PathFinder's addresses carry no site and it offers no site. Every VEuPathDB website, the portal's included, is its own site, and a conversation of another site opens a notice that links it on that site's website. A host no site names uses the deployment's configured site. A site switcher, a website that adds and strips a site segment around PathFinder's paths, and a route tree per site detected on the server were rejected.
tags: [frontend, routing, sites, deployment]
status: stable
---

# What was decided

**An address names a page, never a site.** Every PathFinder route is site-less:
`/conversation`, `/conversation/<id>`, `/conversation/<id>/eda`,
`/conversation/<id>/strategy`, `/conversation/<id>/strategy/step/<stepId>`,
`/saved` and `/audits`; `/` redirects to `/conversation` (`apps/web/src/lib/routes.ts`). Every
VEuPathDB website frames its own PathFinder, so the website is the site, and a site in
the address would only repeat it or contradict it.

**The browser decides the site.** Apache proxies `/pathfinder` with
`ProxyPreserveHost Off`, so the server sees one Host for every website. The browser
compares the page's origin with each site's `siteOrigin` in `GET /api/v1/sites`
(`apps/web/src/lib/sites/currentSite.ts`, read through
`apps/web/src/app/hooks/useCurrentSite.ts`):

- A website works on its own site. This includes the portal's website, where PathFinder
  searches as the portal, across all sites. PathFinder offers no site anywhere.
- A conversation of another site opens a notice that links it on that site's own
  website, on every website.
- A host no site names, which is only local development and test, uses the deployment's
  configured site, the `siteId` of `GET /health/config`.

A list of a researcher's own records follows the same rule. On a component site's
website, `/audits` asks `GET /api/v1/audits?siteId=<site>`, so the server lists only
that site's runs; the table drops its Site column, and an empty list reads "No audits
on <site> yet". On the portal's website, the page lists every site's runs with a Site
column, as that is the portal's own view
(`apps/web/src/features/audit/AuditRunsPage.tsx`).

The app shell mirrors the resolved site into the session store's `selectedSite`,
which the chat runtime and the composer read outside the route. The store persists
nothing.

The Help page follows the same rule. `apps/web/src/app/help/HelpRoute.tsx` reads
`lib/sites/currentSite.ts::currentSiteId`, so the page names the site, and names none
before the site list, the configuration and the page's origin are known.

# What was rejected

**A site switcher.** A switcher on the portal's website or on a host no site names made
one website work on many sites. A conversation then moved the picked site, and a stored
pick decided where the next one started. With every website framing its own PathFinder,
it offered a choice the website already makes.

**The website adds and strips the site segment.** The website page knows its project,
so it could load `/pathfinder/<site>/...` in the frame and show `/app/pathfinder/...`
in the address bar. That keeps a site segment PathFinder no longer needs, and makes
every website translate between its project and PathFinder's site ids for good.

**A route tree per site, chosen on the server.** The server cannot tell the websites
apart behind the proxy, so it would need a header every proxy sets, and the routes
would exist twice.

# What would prove this wrong

A researcher who needs one website to work on another site's records, or a VEuPathDB
website that does not frame its own PathFinder, would bring a choice of site back.

`apps/web/src/lib/sites/currentSite.test.ts` holds the resolution order;
`apps/web/src/app/(app)/layout.test.tsx` requires the portal's website to stay the portal
with a conversation of another site open, the notice for that conversation on every
website, and the configured site on a host no site names.
`apps/web/src/app/components/AppNavRail.test.tsx` requires no site control on the rail.
`apps/web/src/app/(app)/audits/page.test.tsx` requires the site's `siteId` on the audits
read on a component site's website, and none on the portal's.
`apps/web/src/app/help/HelpRoute.test.tsx` requires the Help page to name the site and no
Switch site.
