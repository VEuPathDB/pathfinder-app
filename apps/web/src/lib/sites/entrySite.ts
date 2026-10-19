import type { SiteResponse } from "@pathfinder/shared";

import { hostingSite } from "./hostingSite";

/** The site a site-less entry point opens, or the sites that refused. */
export type EntrySite =
  { kind: "site"; siteId: string } | { kind: "none"; sites: string[] };

/**
 * The site whose website frames PathFinder when it answers, else the
 * deployment's site when it answers, else the portal when it answers, else the
 * first site in the list's order that answers.
 */
export function chooseEntrySite(
  sites: SiteResponse[],
  defaultSiteId: string,
  origin: string | null,
): EntrySite {
  const framing = origin === null ? undefined : hostingSite(sites, origin);
  if (framing?.available === true) return { kind: "site", siteId: framing.id };
  const preferred = sites.find((site) => site.id === defaultSiteId && site.available);
  if (preferred !== undefined) return { kind: "site", siteId: preferred.id };
  const portal = sites.find((site) => site.isPortal && site.available);
  if (portal !== undefined) return { kind: "site", siteId: portal.id };
  const first = sites.find((site) => site.available);
  if (first !== undefined) return { kind: "site", siteId: first.id };
  return { kind: "none", sites: sites.map((site) => site.id) };
}
