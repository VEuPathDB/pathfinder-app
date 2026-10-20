"use client";

import { usePathname } from "next/navigation";
import { useSuspenseQuery } from "@tanstack/react-query";
import type { SiteResponse } from "@pathfinder/shared";

import { usePageOrigin } from "@/app/hooks/usePageOrigin";
import { sitesOptions } from "@/lib/api/sites";
import { conversationIdFromPath } from "@/lib/routes";
import { currentSiteId, lockedSite } from "@/lib/sites/currentSite";
import { useConversationDetail } from "@/state/useConversationExists";
import { useSessionStore } from "@/state/useSessionStore";

export function useCurrentSite(): {
  siteId: string;
  locked: SiteResponse | undefined;
  conversationSite: string | null;
} {
  const { data: sites } = useSuspenseQuery(sitesOptions());
  const origin = usePageOrigin();
  const picked = useSessionStore((s) => s.pickedSite);
  const { data: conversation } = useConversationDetail(
    conversationIdFromPath(usePathname()),
  );
  const conversationSite = conversation?.siteId ?? null;
  return {
    siteId: currentSiteId({ sites, origin, picked, conversationSite }),
    locked: lockedSite(sites, origin),
    conversationSite,
  };
}
