"use client";

import { useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";

import { useSystemConfig } from "@/app/hooks/useSystemConfig";
import { sitesOptions } from "@/lib/api/sites";
import { hostingSite } from "@/lib/sites/hostingSite";

const subscribeToNothing = () => () => {};

export function useSitePages(): { signInUrl: string; pageUrl: string } {
  const { siteSignInUrl, sitePageUrl } = useSystemConfig();
  const { data: sites } = useQuery(sitesOptions());
  const origin = useSyncExternalStore(
    subscribeToNothing,
    () => window.location.origin,
    () => null,
  );
  const framing =
    origin === null || sites === undefined ? undefined : hostingSite(sites, origin);
  return {
    signInUrl: framing?.signInUrl ?? siteSignInUrl,
    pageUrl: framing?.pageUrl ?? sitePageUrl,
  };
}
