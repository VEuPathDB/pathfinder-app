"use client";

import { useRouter } from "next/navigation";
import type { SiteResponse } from "@pathfinder/shared";
import { useIsomorphicLayoutEffect } from "usehooks-ts";

import { chatRoot } from "@/lib/routes";
import { chooseEntrySite } from "@/lib/sites/entrySite";

export function EntrySiteRedirect({
  sites,
  deploymentSiteId,
}: {
  sites: SiteResponse[];
  deploymentSiteId: string;
}) {
  const router = useRouter();
  useIsomorphicLayoutEffect(() => {
    const entry = chooseEntrySite(sites, deploymentSiteId, window.location.origin);
    if (entry.kind === "site") router.replace(chatRoot(entry.siteId));
  }, [sites, deploymentSiteId, router]);
  return null;
}
