"use client";

import { useQuery } from "@tanstack/react-query";

import { usePageOrigin } from "@/app/hooks/usePageOrigin";
import { useSystemConfig } from "@/app/hooks/useSystemConfig";
import { sitesOptions } from "@/lib/api/sites";
import { hostingSite } from "@/lib/sites/hostingSite";

export function useSitePages(): { signInUrl: string; pageUrl: string } {
  const { siteSignInUrl, sitePageUrl } = useSystemConfig();
  const { data: sites } = useQuery(sitesOptions());
  const origin = usePageOrigin();
  const framing =
    origin === null || sites === undefined ? undefined : hostingSite(sites, origin);
  return {
    signInUrl: framing?.signInUrl ?? siteSignInUrl,
    pageUrl: framing?.pageUrl ?? sitePageUrl,
  };
}
