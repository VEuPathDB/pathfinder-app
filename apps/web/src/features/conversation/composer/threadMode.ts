import type { QueryClient } from "@tanstack/react-query";

import { strategyQueryOptions } from "@/lib/api/strategy";
import type { ThreadMode } from "@pathfinder/shared/generated/types/ThreadMode";
import { useConversationDetail } from "@/state/useConversationExists";
import { useThreadModeStore } from "@/state/useThreadModeStore";

export function threadModeFor(
  conversationId: string,
  queryClient: QueryClient,
): ThreadMode {
  const picked = useThreadModeStore.getState().modes[conversationId];
  if (picked !== undefined) return picked;
  return (
    queryClient.getQueryData(strategyQueryOptions(conversationId).queryKey)?.mode ??
    "auto"
  );
}

export function useThreadMode(conversationId: string): ThreadMode {
  const picked = useThreadModeStore((s) => s.modes[conversationId]);
  const { data: detail } = useConversationDetail(conversationId);
  return picked ?? detail?.mode ?? "auto";
}
