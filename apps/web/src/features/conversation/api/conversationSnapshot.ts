import { queryOptions } from "@tanstack/react-query";
import type { UIMessage } from "ai";
import { APIError } from "@/lib/api/http";

import { assistantClient } from "./assistantClient";

interface ConversationSnapshot {
  messages: UIMessage[];
  /** Section 4: the snapshot ends at a prompt, so a turn is still running. */
  turnInFlight: boolean;
}

export async function loadConversationSnapshot(
  conversationId: string,
): Promise<ConversationSnapshot> {
  try {
    const { messages, turnInFlight } = await assistantClient.snapshot(conversationId);
    return { messages, turnInFlight };
  } catch (err) {
    if (err instanceof APIError && err.status === 404) {
      return { messages: [], turnInFlight: false };
    }
    throw err;
  }
}

export function conversationSnapshotOptions(conversationId: string) {
  return queryOptions({
    queryKey: ["conversations", conversationId, "snapshot"] as const,
    queryFn: () => loadConversationSnapshot(conversationId),
    // The transcript grows during a turn. A mount reads it once and keeps that
    // list; the next mount must read it again.
    staleTime: Infinity,
    gcTime: 0,
  });
}
