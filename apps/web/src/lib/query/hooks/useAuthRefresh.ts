"use client";

import { useQuery } from "@tanstack/react-query";
import { authRefreshOptions, authStatusOptions } from "@/lib/api/veupathdb-auth";

/**
 * One internal-token refresh per website sign-in, keyed by site. Returns whether the refresh
 * has settled (success or failure) so consumers can gate dependent queries.
 * Running this hook from multiple components is safe - TanStack Query
 * deduplicates by queryKey.
 */
export function useAuthRefresh(siteId: string): { authRefreshed: boolean } {
  const statusQuery = useQuery(authStatusOptions(siteId));
  const refreshQuery = useQuery({
    ...authRefreshOptions(siteId),
    enabled: statusQuery.data?.signedIn === true,
  });

  return {
    authRefreshed: refreshQuery.isSuccess || refreshQuery.isError,
  };
}
