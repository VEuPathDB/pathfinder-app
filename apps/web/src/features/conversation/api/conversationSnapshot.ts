import { queryOptions } from "@tanstack/react-query";
import type { UIMessage } from "ai";
import { APIError } from "@/lib/api/http";

import { assistantClient } from "./assistantClient";

export async function loadSnapshotMessages(
  conversationId: string,
): Promise<UIMessage[]> {
  try {
    return (await assistantClient.snapshot(conversationId)).messages;
  } catch (err) {
    if (err instanceof APIError && err.status === 404) return [];
    throw err;
  }
}

export function conversationSnapshotOptions(conversationId: string) {
  return queryOptions({
    queryKey: ["conversations", conversationId, "snapshot"] as const,
    queryFn: () => loadSnapshotMessages(conversationId),
    // The transcript grows during a turn. A mount reads it once and keeps that
    // list; the next mount must read it again.
    staleTime: Infinity,
    gcTime: 0,
  });
}
