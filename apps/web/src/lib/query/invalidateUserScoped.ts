import type { QueryClient } from "@tanstack/react-query";

import { queryKeyPrefixes } from "@/lib/query/keys";

/**
 * Invalidate all TanStack Query caches that hold user-scoped data.
 *
 * Call this whenever the auth state changes (login, logout, cookie refresh)
 * so that strategies and gene sets are re-fetched with the current credentials.
 */
export function invalidateUserScopedQueries(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.strategies });
  void queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.geneSets });
}
