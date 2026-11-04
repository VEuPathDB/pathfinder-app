"use client";

import { usePathname } from "next/navigation";
import { useSuspenseQuery } from "@tanstack/react-query";

import { usePageOrigin } from "@/app/hooks/usePageOrigin";
import { useSystemConfig } from "@/app/hooks/useSystemConfig";
import { sitesOptions } from "@/lib/api/sites";
import { conversationIdFromPath } from "@/lib/routes";
import { currentSiteId } from "@/lib/sites/currentSite";
import { useConversationDetail } from "@/state/useConversationExists";

export function useCurrentSite(): {
  siteId: string;
  isPortal: boolean;
  conversationSite: string | null;
} {
  const { data: sites } = useSuspenseQuery(sitesOptions());
  const origin = usePageOrigin();
  const { siteId: configuredSite } = useSystemConfig();
  const { data: conversation } = useConversationDetail(
    conversationIdFromPath(usePathname()),
  );
  const siteId = currentSiteId(sites, origin, configuredSite);
  return {
    siteId,
    isPortal: sites.some((site) => site.id === siteId && site.isPortal),
    conversationSite: conversation?.siteId ?? null,
  };
}
