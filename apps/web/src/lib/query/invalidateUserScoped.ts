import type { QueryClient } from "@tanstack/react-query";
import { getMyQuotaQueryKey } from "@pathfinder/shared/generated/hooks/useGetMyQuota";
import { listDismissedStrategiesQueryKey } from "@pathfinder/shared/generated/hooks/useListDismissedStrategies";
import { listStrategiesQueryKey } from "@pathfinder/shared/generated/hooks/useListStrategies";

import { isStrategyQueryKey } from "@/lib/api/strategy";
import { queryKeyPrefixes } from "@/lib/query/keys";

/**
 * Invalidate all TanStack Query caches that hold user-scoped data.
 *
 * Call this whenever the auth state changes (login, logout, cookie refresh)
 * so that every list, detail and quota read is re-fetched with the current credentials.
 */
export function invalidateUserScopedQueries(queryClient: QueryClient): void {
  for (const queryKey of [
    queryKeyPrefixes.strategies,
    queryKeyPrefixes.geneSets,
    listStrategiesQueryKey(),
    listDismissedStrategiesQueryKey(),
    getMyQuotaQueryKey(),
  ]) {
    void queryClient.invalidateQueries({ queryKey });
  }
  void queryClient.invalidateQueries({
    predicate: (query) => isStrategyQueryKey(query.queryKey),
  });
}
