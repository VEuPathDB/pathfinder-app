"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { systemConfigQueryOptions } from "@pathfinder/shared/generated/hooks/useSystemConfig";

/**
 * Reads whether the backend has a model provider and the deployment's sign-in
 * address. Suspends until the config loads; the nearest ErrorBoundary (app
 * shell) catches a failure.
 */
export function useSystemConfig(): {
  setupRequired: boolean;
  siteSignInUrl: string;
  retry: () => void;
} {
  const { data, refetch } = useSuspenseQuery(systemConfigQueryOptions());
  const setupRequired = data.llmConfigured === false;
  return {
    setupRequired,
    siteSignInUrl: data.siteSignInUrl,
    retry: () => {
      void refetch();
    },
  };
}
