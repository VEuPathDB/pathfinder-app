"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useAuthRefresh } from "@/lib/query/hooks/useAuthRefresh";
import type { ConversationResponse } from "@pathfinder/shared/generated/types/ConversationResponse";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { listDismissedStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListDismissedStrategies";
import { authStatusOptions } from "@/lib/api/veupathdb-auth";

interface UseChatListFetchingArgs {
  siteId: string;
}

export interface ChatListFetchingResult {
  chats: ConversationResponse[];
  dismissedChats: ConversationResponse[];
  isLoading: boolean;
  isFetched: boolean;
  isSyncing: boolean;
  invalidate: () => Promise<void>;
  handleManualRefresh: () => Promise<void>;
}

export function useChatListFetching({
  siteId,
}: UseChatListFetchingArgs): ChatListFetchingResult {
  const { data: authStatus } = useQuery(authStatusOptions(siteId));
  const { authRefreshed } = useAuthRefresh(siteId);
  const queryClient = useQueryClient();

  const [isSyncing, setIsSyncing] = useState(false);

  const queryEnabled = authStatus?.signedIn === true && authRefreshed && siteId !== "";

  const listOpts = listStrategiesQueryOptions({ siteId });
  const dismissedOpts = listDismissedStrategiesQueryOptions({ siteId });

  const listQuery = useQuery({ ...listOpts, enabled: queryEnabled });
  const dismissedQuery = useQuery({ ...dismissedOpts, enabled: queryEnabled });

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: listOpts.queryKey }),
      queryClient.invalidateQueries({ queryKey: dismissedOpts.queryKey }),
    ]);
  };

  const handleManualRefresh = async () => {
    setIsSyncing(true);
    try {
      await invalidate();
    } finally {
      setIsSyncing(false);
    }
  };

  return {
    chats: listQuery.data ?? [],
    dismissedChats: dismissedQuery.data ?? [],
    isLoading: listQuery.isLoading,
    isFetched: listQuery.isFetched,
    isSyncing,
    invalidate,
    handleManualRefresh,
  };
}
