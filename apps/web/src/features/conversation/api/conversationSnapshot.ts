import { queryOptions } from "@tanstack/react-query";
import type { UIMessage } from "ai";
import { reduceSnapshot, webStorageCursorStore } from "@pathfinder/assistant-client";
import { z } from "zod";

import { APIError, requestJson } from "@/lib/api/http";

const SnapshotSchema = z.object({
  chunks: z.array(z.looseObject({ type: z.string() })),
  cursor: z.number(),
});

const cursors = webStorageCursorStore();

export async function loadSnapshotMessages(
  conversationId: string,
): Promise<UIMessage[]> {
  let snapshot: { chunks: unknown[]; cursor: number };
  try {
    snapshot = await requestJson(
      SnapshotSchema,
      `/api/v1/conversations/${conversationId}/events/snapshot`,
    );
  } catch (err) {
    if (err instanceof APIError && err.status === 404) return [];
    throw err;
  }
  cursors.write(conversationId, snapshot.cursor);
  return reduceSnapshot(snapshot.chunks);
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
