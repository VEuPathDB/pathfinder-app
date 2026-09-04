"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  authRefreshOptions,
  authStatusOptions,
  refreshAuth,
} from "@/lib/api/veupathdb-auth";
import { invalidateUserScopedQueries } from "@/lib/query/invalidateUserScoped";

/**
 * One-shot internal-token refresh keyed by site. Returns whether the refresh
 * has settled (success or failure) so consumers can gate dependent queries.
 * Running this hook from multiple components is safe — TanStack Query
 * deduplicates by queryKey.
 */
export function useAuthRefresh(siteId: string): { authRefreshed: boolean } {
  const queryClient = useQueryClient();

  const statusQuery = useQuery(authStatusOptions(siteId));
  const signedIn = statusQuery.data?.signedIn === true;

  const base = authRefreshOptions(siteId);
  const refreshQuery = useQuery({
    ...base,
    queryFn: async () => {
      await refreshAuth(siteId);
      invalidateUserScopedQueries(queryClient);
      return { refreshed: true };
    },
    enabled: signedIn,
  });

  return {
    authRefreshed: refreshQuery.isSuccess || refreshQuery.isError,
  };
}
