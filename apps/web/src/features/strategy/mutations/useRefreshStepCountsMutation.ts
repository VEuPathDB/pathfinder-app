"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { ConversationResponse } from "@pathfinder/shared";
import { refreshStepCounts } from "@pathfinder/shared/generated/hooks/useRefreshStepCounts";

import { toStrategy, writeStrategy } from "@/lib/api/strategy";
import { toUserMessage } from "@/lib/api/errors";

interface UseRefreshStepCountsArgs {
  conversationId: string;
  siteId: string;
}

/**
 * Read every step count from VEuPathDB again and show what it answers.
 *
 * The route stores what it reads, so the answer is the whole conversation and
 * it replaces the one the panel holds.
 */
export function useRefreshStepCountsMutation({
  conversationId,
  siteId,
}: UseRefreshStepCountsArgs) {
  const queryClient = useQueryClient();
  return useMutation<ConversationResponse, Error, void>({
    mutationFn: () => refreshStepCounts(conversationId, { siteId }),
    onSuccess: (response) => {
      writeStrategy(queryClient, conversationId, toStrategy(response));
    },
    onError: (error) => {
      toast.error(toUserMessage(error, "Could not refresh the step counts."));
    },
  });
}
