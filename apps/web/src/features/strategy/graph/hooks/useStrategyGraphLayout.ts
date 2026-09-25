"use client";

import { useState } from "react";
import type { Edge, Node } from "@xyflow/react";
import { useReactFlow } from "@xyflow/react";
import { useQuery } from "@tanstack/react-query";
import { useEventListener } from "usehooks-ts";
import type { Strategy } from "@pathfinder/shared";
import type { StepNodeData } from "@/features/strategy/graph/components/nodes/types";
import { useStrategyHistory } from "@/state/useStrategySelectors";
import { useStrategyCacheUtils } from "@/lib/api/strategy";
import { useNodePositionHistory } from "@/features/strategy/graph/hooks/useNodePositionHistory";
import {
  deserializeStrategyToGraph,
  layoutStrategyGraph,
  type StepPositions,
} from "@/features/strategy/graph";
import {
  useDuplicateStepMutation,
  useUpdateStepMutation,
} from "@/features/strategy/mutations";
import { useApplyOperation } from "@/features/strategy/mutations/useApplyOperation";
import { serializeStrategyAst } from "@/features/strategy/graph/serialize";

interface UseStrategyGraphLayoutOptions {
  strategy: Strategy | null;
  isCompact: boolean;
  nodes: Node[];
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>;
  setEdges: React.Dispatch<React.SetStateAction<Edge[]>>;
  nodePositions: Map<string, { x: number; y: number }>;
  handleOpenDetails: (stepId: string) => void;
  setSelectedNodeIds: (ids: string[]) => void;
  /** Opens the delete-resolution flow; wired into each node's kebab. */
  requestDelete: (stepId: string) => void;
}

function layoutTopologyKey(strategy: Strategy | null): string {
  if (!strategy) return "empty";
  return strategy.steps
    .map((s) => `${s.id}:${s.primaryInputStepId ?? ""}:${s.secondaryInputStepId ?? ""}`)
    .join("|");
}

export function useStrategyGraphLayout(options: UseStrategyGraphLayoutOptions) {
  const {
    strategy,
    isCompact,
    nodes,
    setNodes,
    setEdges,
    nodePositions,
    handleOpenDetails,
    setSelectedNodeIds,
    requestDelete,
  } = options;

  const [layoutSeed, setLayoutSeed] = useState(0);
  const [userHasMoved, setUserHasMoved] = useState(false);
  const { fitView } = useReactFlow();
  const [prevLayoutSeed, setPrevLayoutSeed] = useState(layoutSeed);
  const [prevStrategyId, setPrevStrategyId] = useState<string | null>(
    strategy?.id ?? null,
  );

  const conversationId = strategy?.id ?? "";
  const cache = useStrategyCacheUtils();
  const updateStepMutation = useUpdateStepMutation(conversationId);
  const duplicateStepMutation = useDuplicateStepMutation(conversationId);
  const apply = useApplyOperation(conversationId);
  const { undo, redo, canUndo, canRedo } = useStrategyHistory(conversationId);

  const replayCachedStrategy = (): void => {
    const next = cache.get(conversationId);
    if (!next) return;
    const stepsById = Object.fromEntries(next.steps.map((s) => [s.id, s]));
    const result = serializeStrategyAst(stepsById, next);
    if (!result) return;
    apply.mutate({
      op: {
        kind: "replaceStrategy",
        root: result.plan.root,
        name: next.name,
        ...(next.description !== undefined && {
          description: next.description,
        }),
      },
    });
  };

  const {
    pushSnapshot,
    reset: resetNodeHistory,
    tryUndo,
    tryRedo,
  } = useNodePositionHistory({ setNodes });

  const currentStrategyId = strategy?.id ?? null;
  if (prevStrategyId !== currentStrategyId) {
    setPrevStrategyId(currentStrategyId);
    setUserHasMoved(false);
    setSelectedNodeIds([]);
  }

  const handleUndoRedoKeyDown = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null;
    if (
      target &&
      (target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable)
    ) {
      return;
    }
    if (!(event.ctrlKey || event.metaKey)) return;
    const key = event.key.toLowerCase();
    if (key !== "z" && key !== "y") return;
    event.preventDefault();
    if (key === "y" || event.shiftKey) {
      if (tryRedo()) return;
      if (canRedo()) {
        redo();
        replayCachedStrategy();
      }
      return;
    }
    if (tryUndo()) return;
    if (canUndo()) {
      undo();
      replayCachedStrategy();
    }
  };
  useEventListener("keydown", handleUndoRedoKeyDown);

  const topologyKey = layoutTopologyKey(strategy);
  const { data: computedPositions } = useQuery<StepPositions>({
    queryKey: ["strategy-layout", strategy?.id ?? null, topologyKey],
    queryFn: () => layoutStrategyGraph(strategy),
    enabled: strategy !== null && strategy.steps.length > 0,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const [prevStrategy, setPrevStrategy] = useState<Strategy | null>(strategy);
  const [prevPositions, setPrevPositions] = useState<StepPositions | undefined>(
    computedPositions,
  );
  const inputsChanged =
    prevStrategy !== strategy ||
    prevLayoutSeed !== layoutSeed ||
    prevPositions !== computedPositions;
  if (inputsChanged) {
    const forceRelayout =
      prevLayoutSeed !== layoutSeed || prevStrategyId !== currentStrategyId;
    setPrevStrategy(strategy);
    setPrevLayoutSeed(layoutSeed);
    setPrevPositions(computedPositions);

    if (computedPositions !== undefined) {
      const deserializeOpts: Parameters<typeof deserializeStrategyToGraph>[2] = {
        computedPositions,
        existingPositions: nodePositions,
      };
      if (forceRelayout) {
        deserializeOpts.forceRelayout = true;
      }
      const { nodes: rawNodes, edges: newEdges } = deserializeStrategyToGraph(
        strategy,
        handleOpenDetails,
        deserializeOpts,
      );
      // deserialize wires open-details; the node-level
      // delete/duplicate/rename actions attach here.
      const newNodes = rawNodes.map((node) => ({
        ...node,
        data: {
          ...(node.data as StepNodeData),
          onDelete: requestDelete,
          onDuplicate: (stepId: string) => duplicateStepMutation.mutate({ stepId }),
          onRename: (stepId: string, nextName: string) =>
            updateStepMutation.mutate({ stepId, patch: { displayName: nextName } }),
        },
      }));
      setNodes(newNodes);
      setEdges(newEdges);
      if (forceRelayout) {
        resetNodeHistory(newNodes);
      }
      if (
        !isCompact &&
        !userHasMoved &&
        (forceRelayout || newNodes.length > nodes.length)
      ) {
        queueMicrotask(() => void fitView({ padding: 0.3, duration: 300 }));
      }
    }
  }

  const handleNodeDragStop = () => {
    pushSnapshot(nodes);
  };

  const handleRelayout = () => {
    setLayoutSeed((prev) => prev + 1);
  };

  const handleMoveStart = () => {
    setUserHasMoved(true);
  };

  return {
    handleNodeDragStop,
    handleRelayout,
    handleMoveStart,
  } as const;
}
