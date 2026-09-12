"use client";

import { type UseQueryResult, useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useState } from "react";

import type { Strategy } from "@pathfinder/shared";
import { strategyQueryOptions } from "@/lib/api/strategy";
import { conversationIdFromPath } from "@/lib/routes";

import { useSessionStore } from "./useSessionStore";

/**
 * True once the conversation has a row: the caller opened on it, or an action
 * in this tab created it. A draft has no row, so nothing may read it.
 *
 * The route is read at mount and not again, because a draft rewrites its URL
 * when its first turn starts, which is before the row exists. A caller whose
 * conversation changes while it stays mounted therefore learns of the new one
 * only when this tab creates it.
 */
export function useConversationExists(conversationId: string | null): boolean {
  const pathname = usePathname();
  const [openedOnRow] = useState(
    () =>
      conversationId !== null && conversationIdFromPath(pathname) === conversationId,
  );
  const created = useSessionStore((s) => s.createdConversationId === conversationId);
  return conversationId !== null && (openedOnRow || created);
}

/** The conversation detail, read only once the conversation exists. */
export function useConversationDetail(
  conversationId: string | null,
): UseQueryResult<Strategy | null> {
  const exists = useConversationExists(conversationId);
  return useQuery({
    ...strategyQueryOptions(conversationId ?? ""),
    enabled: exists,
  });
}
