"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { client } from "@/lib/api/client";
import type { SaveSubstrategyRequest } from "@pathfinder/shared/generated/types/SaveSubstrategyRequest";
import { openStrategy } from "@pathfinder/shared/generated/hooks/useOpenStrategy";
import { listStrategiesQueryOptions } from "@pathfinder/shared/generated/hooks/useListStrategies";
import { toUserMessage } from "@/lib/api/errors";

export interface SaveSubstrategyVars {
  stepId: string;
  name: string;
  description?: string | null;
}

export interface SaveSubstrategyResult {
  wdkStrategyId: number;
  name: string;
  description: string | null;
  recordType: string;
  rootStepId: number;
}

interface UseSaveSubstrategyArgs {
  conversationId: string;
  siteId: string;
  onSuccess?: (result: SaveSubstrategyResult) => void;
}

export function useSaveSubstrategyMutation({
  conversationId,
  siteId,
  onSuccess,
}: UseSaveSubstrategyArgs) {
  const queryClient = useQueryClient();
  return useMutation<SaveSubstrategyResult, Error, SaveSubstrategyVars>({
    mutationFn: async (vars) => {
      const resp = await client<SaveSubstrategyResult>({
        method: "post",
        url: `/api/v1/conversations/${conversationId}/save-substrategy`,
        params: { siteId },
        data: {
          stepId: vars.stepId,
          name: vars.name,
          description: vars.description ?? null,
        } satisfies SaveSubstrategyRequest,
      });
      // Pull the new WDK strategy into the local conversations table so it
      // appears in the sidebar's Saved group + library page immediately.
      await openStrategy({
        siteId,
        wdkStrategyId: resp.data.wdkStrategyId,
      });
      return resp.data;
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({
        queryKey: listStrategiesQueryOptions({ siteId }).queryKey,
      });
      toast.success("Saved as reusable strategy", { description: data.name });
      onSuccess?.(data);
    },
    onError: (error) => {
      toast.error("Save failed", { description: toUserMessage(error) });
    },
  });
}
