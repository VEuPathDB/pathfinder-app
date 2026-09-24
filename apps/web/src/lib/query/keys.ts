/**
 * Broad prefix constants for TanStack Query cache invalidation.
 *
 * Exact query keys are co-located with their fetch functions via
 * `queryOptions()` in each API module. These prefixes exist solely
 * for broad invalidation (e.g. "invalidate all strategy queries").
 */
export const queryKeyPrefixes = {
  strategies: ["strategies"] as const,
  geneSets: ["gene-sets"] as const,
} as const;
