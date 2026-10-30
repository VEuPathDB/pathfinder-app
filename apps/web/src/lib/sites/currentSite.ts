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

export type SiteFrame =
  { kind: "unknown" } | { kind: "switchable" } | { kind: "locked"; siteId: string };

export function siteFrame(
  sites: SiteResponse[] | undefined,
  origin: string | null,
): SiteFrame {
  if (sites === undefined || origin === null) return { kind: "unknown" };
  const locked = lockedSite(sites, origin);
  return locked === undefined
    ? { kind: "switchable" }
    : { kind: "locked", siteId: locked.id };
}
