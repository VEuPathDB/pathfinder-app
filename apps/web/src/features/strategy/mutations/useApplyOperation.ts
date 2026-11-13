"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { Patch } from "immer";
import type { ConversationResponse, Strategy } from "@strategist/shared";
import { applyOperationEndpoint } from "@strategist/shared/generated/hooks/useApplyOperationEndpoint";
import {
  refetchStrategy,
  strategyQueryKey,
  toStrategy,
  writeStrategy,
} from "@/lib/api/strategy";
import { toUserMessage } from "@/lib/api/errors";
import { applyOperation, type GraphOperation } from "@/features/strategy/operations";
import { toWireOperation } from "@/features/strategy/operations/toWire";
import { useStrategyStore } from "@/state/strategy/store";

export interface ApplyOperationVars {
  op: GraphOperation;
}

interface ApplyContext {
  snapshot: Strategy | null;
  pushed: Patch[] | null;
  siteId: string;
  key: ReturnType<typeof strategyQueryKey>;
}

const STEP_SAVE_KINDS = new Set<GraphOperation["kind"]>([
  "updateStepParams",
  "updateCombineOperator",
  "updateStepMeta",
]);

function failureLead(op: GraphOperation): string {
  return STEP_SAVE_KINDS.has(op.kind)
    ? "The step could not be saved"
    : "Operation failed";
}

export const APPLY_OPERATION_MUTATION_KEY = ["strategy", "operation"] as const;
const APPLY_OPERATION_SCOPE_ID = "strategy-operation";

export function useApplyOperation(conversationId: string) {
  const queryClient = useQueryClient();

  return useMutation<ConversationResponse, Error, ApplyOperationVars, ApplyContext>({
    mutationKey: [...APPLY_OPERATION_MUTATION_KEY, conversationId],
    scope: { id: APPLY_OPERATION_SCOPE_ID },
    onMutate: ({ op }) => {
      const key = strategyQueryKey(conversationId);
      const snapshot = queryClient.getQueryData<Strategy>(key) ?? null;
      const siteId = snapshot?.siteId ?? "";
      let pushed: Patch[] | null = null;
      if (snapshot !== null) {
        const result = applyOperation(snapshot, op);
        if (result.kind === "applied") {
          pushed = useStrategyStore
            .getState()
            .pushSnapshot({ strategy: snapshot }, result.next);
          queryClient.setQueryData<Strategy>(key, result.next);
        }
      }
      return { snapshot, pushed, siteId, key };
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
    onSuccess: (response) => {
      writeStrategy(queryClient, conversationId, toStrategy(response));
      useStrategyStore.getState().setLastFailedOperation(null);
    },
    onError: (err, vars, context) => {
      if (context !== undefined) {
        queryClient.setQueryData<Strategy | null>(context.key, context.snapshot);
        if (context.pushed !== null) {
          useStrategyStore.getState().dropSnapshot(context.pushed);
        }
      }
      void refetchStrategy(queryClient, conversationId);
      useStrategyStore.getState().setLastFailedOperation({ op: vars.op });
      toast.error(toUserMessage(err, failureLead(vars.op)));
    },
  });
}
