"use client";

import { useQuery } from "@tanstack/react-query";

import { usePageOrigin } from "@/app/hooks/usePageOrigin";
import { HelpPage } from "@/features/help/HelpPage";
import { sitesOptions } from "@/lib/api/sites";
import { siteFrame } from "@/lib/sites/currentSite";

export function HelpRoute() {
  const { data: sites } = useQuery(sitesOptions());
  const origin = usePageOrigin();
  return <HelpPage site={siteFrame(sites, origin)} />;
}
