import type { SiteResponse } from "@strategist/shared";

export function siteAppUrl(site: SiteResponse, path: string): string {
  return `${site.baseUrl.replace(/\/service$/, "")}${path}`;
}
