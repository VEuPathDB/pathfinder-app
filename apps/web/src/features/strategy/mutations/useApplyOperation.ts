"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { ConversationResponse, Strategy } from "@pathfinder/shared";
import { applyOperationEndpoint } from "@pathfinder/shared/generated/hooks/useApplyOperationEndpoint";
import { strategyQueryKey, toStrategy } from "@/lib/api/strategy";
import { toUserMessage } from "@/lib/api/errors";
import { applyOperation, type GraphOperation } from "@/features/strategy/operations";
import { toWireOperation } from "@/features/strategy/operations/toWire";
import { useStrategyStore } from "@/state/strategy/store";

export interface ApplyOperationVars {
  op: GraphOperation;
}

interface ApplyContext {
  snapshot: Strategy | null;
  siteId: string;
  key: ReturnType<typeof strategyQueryKey>;
}

class SyncPausedError extends Error {
  constructor() {
    super("Sync paused - record-type mismatch");
    this.name = "SyncPausedError";
  }
}

export const APPLY_OPERATION_MUTATION_KEY = ["strategy", "operation"] as const;
const APPLY_OPERATION_SCOPE_ID = "strategy-operation";

export function useApplyOperation(conversationId: string) {
  const queryClient = useQueryClient();

  return useMutation<ConversationResponse, Error, ApplyOperationVars, ApplyContext>({
    mutationKey: [...APPLY_OPERATION_MUTATION_KEY, conversationId],
    scope: { id: APPLY_OPERATION_SCOPE_ID },
    onMutate: ({ op }) => {
      const validationPaused =
        useStrategyStore.getState().graphValidationStatus[conversationId] === true;
      if (validationPaused) {
        toast.warning("Sync paused - record-type mismatch");
        throw new SyncPausedError();
      }
      const key = strategyQueryKey(conversationId);
      const snapshot = queryClient.getQueryData<Strategy>(key) ?? null;
      const siteId = snapshot?.siteId ?? "";
      if (snapshot !== null) {
        const result = applyOperation(snapshot, op);
        if (result.kind === "applied") {
          useStrategyStore.getState().pushSnapshot({ strategy: snapshot }, result.next);
          queryClient.setQueryData<Strategy>(key, result.next);
        }
      }
      return { snapshot, siteId, key };
    },
    mutationFn: async ({ op }) => {
      const key = strategyQueryKey(conversationId);
      const snapshot = queryClient.getQueryData<Strategy>(key) ?? null;
      const siteId = snapshot?.siteId ?? "";
      return await applyOperationEndpoint(
        conversationId,
        { op: toWireOperation(op) },
        { siteId },
      );
    },
    onSuccess: (response, _vars, context) => {
      queryClient.setQueryData<Strategy>(context.key, toStrategy(response));
      useStrategyStore.getState().setLastFailedOperation(null);
    },
    onError: (err, vars, context) => {
      if (context !== undefined) {
        queryClient.setQueryData<Strategy | null>(context.key, context.snapshot);
      }
      if (err instanceof SyncPausedError) {
        return;
      }
      useStrategyStore.getState().setLastFailedOperation({ op: vars.op });
      toast.error(toUserMessage(err, "Operation failed"));
    },
  });
}
