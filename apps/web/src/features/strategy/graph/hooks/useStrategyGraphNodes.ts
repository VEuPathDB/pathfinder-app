"use client";

import { useState } from "react";
import { type Node, type Edge, useNodesState, useEdgesState } from "@xyflow/react";
import type { Step, Strategy } from "@pathfinder/shared";
import { useStrategyStore } from "@/state/strategy/store";
import { stepsById } from "@/state/strategy/selectors";
import { validateStepsForSave } from "@/features/strategy/validation/save";
import { useSaveValidation } from "@/features/strategy/validation/useSaveValidation";
import {
  getCombineMismatchGroups,
  inferStepKind,
  serializeStrategyAst,
} from "@/features/strategy/graph";

interface UseStrategyGraphNodesOptions {
  strategy: Strategy | null;
  siteId: string;
  variant: "full" | "compact";
}

/**
 * Manages node/edge state arrays, combine-mismatch
 * groups, warning overlay nodes, and step validation.
 */
export function useStrategyGraphNodes(options: UseStrategyGraphNodesOptions) {
  const { strategy, siteId } = options;

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  // Hold only the id: the step itself is derived from the live strategy
  // below, so a saved edit is reflected immediately. Storing the object
  // froze it at selection time and left the editor footer reporting
  // "Edited: N changes" against values that had already been saved.
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);

  // Keep React Flow's per-node `selected` flag in sync with the
  // app-level `selectedStep` so programmatic selection (URL focus,
  // rail click, keyboard shortcut) lights up the visual selected ring
  // — not just opens the editor sheet.
  const setSelectedStep = (step: Step | null): void => {
    setSelectedStepId(step?.id ?? null);
    const targetId = step?.id ?? null;
    setNodes((current) =>
      current.map((n) =>
        n.selected === (n.id === targetId) ? n : { ...n, selected: n.id === targetId },
      ),
    );
  };
  const nodePositions = new Map(
    nodes.map((n: Node) => [n.id, { x: n.position.x, y: n.position.y }]),
  );

  const applyStepValidationErrors = useStrategyStore(
    (state) => state.applyStepValidationErrors,
  );
  const stepsByIdMap = stepsById(strategy);
  const setGraphValidationStatus = useStrategyStore(
    (state) => state.setGraphValidationStatus,
  );

  const editableSteps = strategy?.steps ?? [];
  // Derived, never stored: a step deleted elsewhere deselects itself, and an
  // edited step is seen with its new values on the very next render.
  const selectedStep = editableSteps.find((step) => step.id === selectedStepId) ?? null;

  const buildStepSignature = (step: Step) => {
    const kind = inferStepKind(step);
    return JSON.stringify({
      kind,
      displayName: step.displayName,
      searchName: step.searchName,
      operator: step.operator,
      parameters: step.parameters ?? {},
      primaryInputStepId: step.primaryInputStepId,
      secondaryInputStepId: step.secondaryInputStepId,
      recordType: step.recordType,
    });
  };

  const combineMismatchGroups = getCombineMismatchGroups(editableSteps);

  const planResult = serializeStrategyAst(stepsByIdMap, strategy);
  const planHash = planResult ? JSON.stringify(planResult.plan) : null;
  const graphIdForValidation = strategy?.id ?? null;
  const graphHasValidationIssues = useStrategyStore((state) =>
    graphIdForValidation != null && graphIdForValidation !== ""
      ? state.graphValidationStatus[graphIdForValidation] === true
      : false,
  );

  const renderNodes = nodes;

  const validateSearchSteps = async () => {
    const steps = editableSteps;
    if (steps.length === 0) return true;
    const { errorsByStepId, hasErrors: hasFieldErrors } = await validateStepsForSave({
      siteId,
      steps,
      strategy,
    });
    applyStepValidationErrors(errorsByStepId);
    const hasErrors = hasFieldErrors || combineMismatchGroups.length > 0;
    const graphId = strategy?.id;
    if (graphId != null && graphId !== "") {
      setGraphValidationStatus(graphId, hasErrors);
    }
    return !hasErrors;
  };

  useSaveValidation({
    steps: editableSteps,
    buildStepSignature,
    validate: validateSearchSteps,
  });

  return {
    nodes,
    setNodes,
    onNodesChange,
    edges,
    setEdges,
    onEdgesChange,
    nodePositions,
    renderNodes,
    selectedStep,
    setSelectedStep,
    editableSteps,
    planResult,
    planHash,
    graphHasValidationIssues,
    combineMismatchGroups,
    validateSearchSteps,
    buildStepSignature,
  } as const;
}
