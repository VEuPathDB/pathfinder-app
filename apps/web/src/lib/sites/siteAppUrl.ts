import type { SiteResponse } from "@pathfinder/shared";

export function siteAppUrl(site: SiteResponse, path: string): string {
  return `${site.baseUrl.replace(/\/service$/, "")}${path}`;
}
