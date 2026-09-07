import type { SiteResponse } from "@pathfinder/shared";

/**
 * Whether the api reports this site's catalog as not loaded. A site the list
 * does not name is not refused: the api answers its routes.
 */
export function siteIsDown(sites: SiteResponse[], siteId: string): boolean {
  return sites.some((site) => site.id === siteId && !site.available);
}
