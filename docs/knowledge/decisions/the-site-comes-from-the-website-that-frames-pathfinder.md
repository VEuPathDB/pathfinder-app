---
type: Decision
title: The site comes from the website that frames PathFinder
description: PathFinder's addresses carry no site. A component site's website locks PathFinder to that site with no site switcher; the portal's website and a host no site names keep the switcher, where an open conversation works on its own site and a new one on the picked site. A website that adds and strips a site segment around PathFinder's paths, and a route tree per site detected on the server, were rejected.
tags: [frontend, routing, sites, deployment]
status: stable
---

# What was decided

**An address names a page, never a site.** Every PathFinder route is site-less:
`/conversation`, `/conversation/<id>`, `/conversation/<id>/eda`,
`/conversation/<id>/strategy`, `/conversation/<id>/strategy/step/<stepId>`,
`/saved` and `/audits`; `/` redirects to `/conversation` (`apps/web/src/lib/routes.ts`). Once every
VEuPathDB website frames its own PathFinder, the website is the site, and a site in
the address would only repeat it or contradict it.

**The browser decides the site.** Apache proxies `/pathfinder` with
`ProxyPreserveHost Off`, so the server sees one Host for every website. The browser
compares the page's origin with each site's `siteOrigin` in `GET /api/v1/sites`
(`apps/web/src/lib/sites/currentSite.ts`, read through
`apps/web/src/app/hooks/useCurrentSite.ts`):

- A component site's website locks PathFinder to that site. The nav rail shows no
  site switcher, and a conversation of another site opens a notice that links it on
  that site's own website.
- The portal's website and a host no site names, such as local development, keep the
  switcher until every component site frames its own PathFinder. There an open
  conversation works on its own site, and a new conversation on the picked site,
  which the session store persists (`pickedSite`) and an opened conversation of
  another site replaces.

A list of a researcher's own records follows the same rule. On a component site's
website, `/audits` asks `GET /api/v1/audits?siteId=<site>`, so the server lists only
that site's runs; the table drops its Site column, and an empty list reads "No audits
on <site> yet". On the portal's website, the page lists every site's runs with a Site
column (`apps/web/src/features/audit/AuditRunsPage.tsx`).

The app shell mirrors the resolved site into the session store's `selectedSite`,
which the chat runtime and the composer read outside the route.

The Help page follows the same rule. `apps/web/src/app/help/HelpRoute.tsx` reads
`lib/sites/currentSite.ts::siteFrame`, so the page names the locked site on a component
site's website, names Switch site where the switcher shows, and names neither before the
site list and the page's origin are known.

# What was rejected

**The website adds and strips the site segment.** The website page knows its project,
so it could load `/pathfinder/<site>/...` in the frame and show `/app/pathfinder/...`
in the address bar. That keeps a site segment PathFinder no longer needs, and makes
every website translate between its project and PathFinder's site ids for good.

**A route tree per site, chosen on the server.** The server cannot tell the websites
apart behind the proxy, so it would need a header every proxy sets, and the routes
would exist twice until the portal stops offering the switcher.

# What would prove this wrong

`apps/web/src/lib/sites/currentSite.test.ts` holds the resolution order;
`apps/web/src/app/(app)/layout.test.tsx` requires no switcher on a component site's
website, the notice for another site's conversation, and the switch on a website that
offers it.
`apps/web/src/app/(app)/audits/page.test.tsx` requires the locked site's `siteId` on
the audits read, and none on the portal.
`apps/web/src/app/help/HelpRoute.test.tsx` requires no Switch site on the Help page on a
component site's website, and Switch site on the portal's.
