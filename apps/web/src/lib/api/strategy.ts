"use client";

import {
  queryOptions,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import type { ConversationResponse, Strategy } from "@pathfinder/shared";
import { getStepRecordsQueryKey } from "@pathfinder/shared/generated/hooks/useGetStepRecords";
import { getStrategy } from "@pathfinder/shared/generated/hooks/useGetStrategy";

import { APIError } from "./http";

export function toStrategy(response: ConversationResponse): Strategy {
  return {
    ...response,
    steps: response.steps ?? [],
    rootStepId: response.rootStepId ?? null,
    recordType: response.recordType ?? null,
    isSaved: response.isSaved ?? false,
  };
}

export function strategyQueryKey(conversationId: string) {
  return ["conversations", conversationId, "detail"] as const;
}

/** The key prefix every step answer page of one conversation shares. */
function stepRecordsKeyPrefix(conversationId: string) {
  const [route] = getStepRecordsQueryKey(conversationId, undefined, { siteId: "" });
  return [{ url: route.url, params: { conversation_id: conversationId } }] as const;
}

/**
 * Store a strategy the server answered. A read still in flight began before this
 * answer, so it is cancelled; every step answer read before it is stale.
 */
export function writeStrategy(
  client: QueryClient,
  conversationId: string,
  strategy: Strategy,
): void {
  void client.cancelQueries({ queryKey: strategyQueryKey(conversationId) });
  client.setQueryData<Strategy>(strategyQueryKey(conversationId), strategy);
  void client.invalidateQueries({ queryKey: stepRecordsKeyPrefix(conversationId) });
}

/** Read the strategy again, and every step answer with it. */
export async function refetchStrategy(
  client: QueryClient,
  conversationId: string,
): Promise<void> {
  await Promise.all([
    client.invalidateQueries({ queryKey: strategyQueryKey(conversationId) }),
    client.invalidateQueries({ queryKey: stepRecordsKeyPrefix(conversationId) }),
  ]);
}

/** The caller's conversation, or null when there is none: a conversation that
 *  belongs to another user is refused with 403 and is none of the caller's. */
async function fetchStrategy(conversationId: string): Promise<Strategy | null> {
  try {
    const raw = await getStrategy(conversationId);
    return toStrategy(raw);
  } catch (err) {
    if (err instanceof APIError && (err.status === 404 || err.status === 403)) {
      return null;
    }
    throw err;
  }
}

export function strategyQueryOptions(conversationId: string) {
  return queryOptions({
    queryKey: strategyQueryKey(conversationId),
    queryFn: () => fetchStrategy(conversationId),
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

export function useStrategyQuery(conversationId: string) {
  return useQuery(strategyQueryOptions(conversationId));
}

export function useStrategyData(conversationId: string): Strategy | null {
  const { data } = useStrategyQuery(conversationId);
  return data ?? null;
}

export function useStrategyCacheUtils() {
  const client = useQueryClient();
  return {
    get: (id: string): Strategy | null =>
      client.getQueryData<Strategy>(strategyQueryKey(id)) ?? null,
    set: (id: string, next: Strategy | null) =>
      client.setQueryData<Strategy | null>(strategyQueryKey(id), next),
  };
}
