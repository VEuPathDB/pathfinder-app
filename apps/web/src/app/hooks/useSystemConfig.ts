"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { systemConfigQueryOptions } from "@pathfinder/shared/generated/hooks/useSystemConfig";

/**
 * Reads whether the backend has a model provider, the deployment's site, its
 * sign-in address and the website page that frames Strategist. Suspends until the config loads; the nearest ErrorBoundary (app
 * shell) catches a failure.
 */
export function useSystemConfig(): {
  setupRequired: boolean;
  siteId: string;
  siteSignInUrl: string;
  sitePageUrl: string;
  retry: () => void;
} {
  const { data, refetch } = useSuspenseQuery(systemConfigQueryOptions());
  const setupRequired = data.llmConfigured === false;
  return {
    setupRequired,
    siteId: data.siteId,
    siteSignInUrl: data.siteSignInUrl,
    sitePageUrl: data.sitePageUrl,
    retry: () => {
      void refetch();
    },
  };
}
