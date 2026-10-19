import type { SiteResponse } from "@pathfinder/shared";

export function hostingSite(
  sites: SiteResponse[],
  origin: string,
): SiteResponse | undefined {
  return sites.find((site) => site.siteOrigin === origin);
}
