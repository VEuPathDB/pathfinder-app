"use client";

import { useQuery } from "@tanstack/react-query";

import { getMyProviderKeysQueryOptions } from "@pathfinder/shared/generated/hooks/useGetMyProviderKeys";
import type { Payers } from "@/lib/models/payers";

export interface ProviderPayers {
  /** Who pays for each provider, or undefined while signed out or unread. */
  payers: Payers | undefined;
  /** The providers whose stored key was refused. */
  refused: string[];
}

/**
 * The reader's payers. A signed-out reader has none, so the read is silent
 * and every view falls back to the deployment's own view of the catalog.
 */
export function useProviderPayers(): ProviderPayers {
  const { data } = useQuery({
    ...getMyProviderKeysQueryOptions(),
    retry: false,
    meta: { silent: true },
  });
  return {
    payers: data?.payers,
    refused: (data?.keys ?? [])
      .filter((key) => key.status === "refused")
      .map((key) => key.provider),
  };
}
