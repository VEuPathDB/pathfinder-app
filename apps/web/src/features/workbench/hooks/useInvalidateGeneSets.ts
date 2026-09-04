import { useQueryClient } from "@tanstack/react-query";
import { queryKeyPrefixes } from "@/lib/query/keys";

/**
 * Returns a callback that invalidates all gene-set queries.
 *
 * Call this after any mutation (create, delete, set-operation) so TanStack
 * Query refetches the list from the server.
 */
export function useInvalidateGeneSets() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeyPrefixes.geneSets });
}
