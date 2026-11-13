import type { SiteResponse } from "@strategist/shared";

import { hostingSite } from "./hostingSite";

export function currentSiteId(
  sites: SiteResponse[],
  origin: string | null,
  configuredSite: string,
): string {
  const host = origin === null ? undefined : hostingSite(sites, origin);
  return host?.id ?? configuredSite;
}
