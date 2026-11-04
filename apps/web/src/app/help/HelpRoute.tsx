"use client";

import { useQuery } from "@tanstack/react-query";
import { systemConfigQueryOptions } from "@pathfinder/shared/generated/hooks/useSystemConfig";

import { usePageOrigin } from "@/app/hooks/usePageOrigin";
import { HelpPage } from "@/features/help/HelpPage";
import { sitesOptions } from "@/lib/api/sites";
import { currentSiteId } from "@/lib/sites/currentSite";

export function HelpRoute() {
  const { data: sites } = useQuery(sitesOptions());
  const { data: config } = useQuery(systemConfigQueryOptions());
  const origin = usePageOrigin();
  const known = sites !== undefined && config !== undefined && origin !== null;
  return (
    <HelpPage siteId={known ? currentSiteId(sites, origin, config.siteId) : null} />
  );
}
