"use client";

import { toast } from "sonner";
import type { Connection, Edge } from "@xyflow/react";
import type { Step } from "@pathfinder/shared";
import {
  buildGraphIndices,
  getConnectionEffect,
  inferCombineRecordTypeOrMismatch,
  isValidGraphConnection,
} from "@/features/strategy/graph/utils/graphConnectionsLogic";
import { operatorName } from "@/features/strategy/graph/utils/stepTitle";
import { useAddStepMutation } from "@/features/strategy/mutations";
import { useApplyOperation } from "@/features/strategy/mutations/useApplyOperation";

interface UseGraphConnectionsArgs {
  steps: Step[];
  conversationId: string;
}

const COMBINE_MISMATCH_ERROR = "Cannot combine steps with different record types.";
const generateStepId = () => `step_${Math.random().toString(16).slice(2, 10)}`;

/**
 * Connection handlers for the strategy graph.
 *
 * The pre-overhaul "pick combine operator first" modal flow is gone; dragging
 * an edge between two roots now creates a combine step with the default
 * `INTERSECT` operator. The user picks a different operator from the editor
 * Sheet (or the edge ContextMenu) afterwards.
 */
export function useGraphConnections({
  steps,
  conversationId,
}: UseGraphConnectionsArgs) {
  const addStep = useAddStepMutation(conversationId);
  const apply = useApplyOperation(conversationId);
  const indices = buildGraphIndices(steps);

  const isValidConnection = (connection: Edge | Connection) =>
    isValidGraphConnection(connection as Connection, indices);

  const handleConnect = (connection: Connection) => {
    const effect = getConnectionEffect(connection, indices);
    if (effect.type === "patch") {
      const slotKey: keyof typeof effect.patch =
        "primaryInputStepId" in effect.patch
          ? "primaryInputStepId"
          : "secondaryInputStepId";
      const sourceId = effect.patch[slotKey];
      if (typeof sourceId !== "string") return;
      const slot: "primary" | "secondary" =
        slotKey === "primaryInputStepId" ? "primary" : "secondary";
      apply.mutate({
        op: {
          kind: "wireInput",
          targetStepId: effect.targetId,
          slot,
          sourceStepId: sourceId,
        },
      });
      return;
    }
    if (effect.type === "pendingCombine") {
      const { recordType, mismatch } = inferCombineRecordTypeOrMismatch({
        sourceId: effect.sourceId,
        targetId: effect.targetId,
        indices,
      });
      if (mismatch) {
        toast.error(COMBINE_MISMATCH_ERROR);
        return;
      }
      const newStep: Step = {
        id: generateStepId(),
        kind: "combine",
        displayName: operatorName("INTERSECT"),
        operator: "INTERSECT",
        recordType: recordType ?? null,
        primaryInputStepId: effect.sourceId,
        secondaryInputStepId: effect.targetId,
        isFiltered: false,
      };
      addStep.mutate({ step: newStep });
    }
  };

  const handleDeleteEdge = (edge: Edge) => {
    const slot: "primary" | "secondary" =
      edge.targetHandle === "left-secondary" || edge.id.endsWith("-secondary")
        ? "secondary"
        : "primary";
    apply.mutate({
      op: {
        kind: "deleteEdge",
        sourceId: edge.source,
        targetId: edge.target,
        slot,
        resolution: "detach",
      },
    });
  };

  const startCombine = (sourceId: string, targetId: string) => {
    if (!sourceId || !targetId || sourceId === targetId) return;
    if (indices.rootIds.length === 1) return;
    if (!indices.rootSet.has(sourceId) || !indices.rootSet.has(targetId)) return;
    const { recordType, mismatch } = inferCombineRecordTypeOrMismatch({
      sourceId,
      targetId,
      indices,
    });
    if (mismatch) {
      toast.error(COMBINE_MISMATCH_ERROR);
      return;
    }
    const newStep: Step = {
      id: generateStepId(),
      kind: "combine",
      displayName: operatorName("INTERSECT"),
      operator: "INTERSECT",
      recordType: recordType ?? null,
      primaryInputStepId: sourceId,
      secondaryInputStepId: targetId,
      isFiltered: false,
    };
    addStep.mutate({ step: newStep });
  };

  return {
    isValidConnection,
    handleConnect,
    handleDeleteEdge,
    startCombine,
  };
}
