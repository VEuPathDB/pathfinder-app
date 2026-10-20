import type { SiteResponse } from "@pathfinder/shared";

import { hostingSite } from "./hostingSite";

export function lockedSite(
  sites: SiteResponse[],
  origin: string | null,
): SiteResponse | undefined {
  const host = origin === null ? undefined : hostingSite(sites, origin);
  return host?.isPortal === false ? host : undefined;
}

export function currentSiteId({
  sites,
  origin,
  picked,
  conversationSite,
}: {
  sites: SiteResponse[];
  origin: string | null;
  picked: string;
  conversationSite: string | null;
}): string {
  return lockedSite(sites, origin)?.id ?? conversationSite ?? picked;
}
