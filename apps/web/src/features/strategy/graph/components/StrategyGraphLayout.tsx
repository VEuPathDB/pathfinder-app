"use client";

import {
  ReactFlow,
  Background,
  ConnectionMode,
  Panel,
  SelectionMode,
  type EdgeTypes,
  type NodeTypes,
} from "@xyflow/react";
import type { Step } from "@pathfinder/shared";
import { StepNode } from "@/features/strategy/graph/components/nodes/StepNode";
import { CanvasControls } from "@/features/strategy/graph/components/CanvasControls";
import { OrphanNotice } from "@/features/strategy/graph/components/OrphanNotice";
import { SelectionActionBar } from "@/features/strategy/graph/components/SelectionActionBar";
import { SmartMiniMap } from "@/features/strategy/graph/components/SmartMiniMap";
import { StepEdge } from "@/features/strategy/graph/components/edges/StepEdge";
import { ValidationAlert } from "@/features/strategy/graph/components/ValidationAlert";
import { useStrategyGraphCtx } from "@/features/strategy/graph/StrategyGraphContext";
import { isNodeToolbarOrMenuTarget } from "@/features/strategy/graph/nodeClickTarget";
import { usePrefersReducedMotion } from "@/lib/motion";
import { findOrphanSteps } from "@/features/strategy/graph";
import { useStrategyStore } from "@/state/strategy/store";

const NODE_TYPES: NodeTypes = {
  step: StepNode,
};
const EDGE_TYPES: EdgeTypes = {
  step: StepEdge,
};
const FIT_VIEW_OPTIONS = { padding: 0.3 } as const;
const SNAP_GRID: [number, number] = [28, 28];

export function StrategyGraphLayout() {
  const g = useStrategyGraphCtx();
  const strategyId = g.strategy?.id ?? "";
  const isPaused = useStrategyStore(
    (s) => s.graphValidationStatus[strategyId] === true,
  );
  const reducedMotion = usePrefersReducedMotion();

  const handleViewMismatch = (firstStepId: string): void => {
    const step = g.editableSteps.find((item) => item.id === firstStepId);
    if (step !== undefined) {
      g.setSelectedStep(step);
    }
  };

  const orphanSteps = findOrphanSteps(
    g.strategy?.steps ?? [],
    g.strategy?.rootStepId ?? null,
  );
  const firstOrphanId = orphanSteps[0]?.id ?? null;
  const handleOrphanView = (stepId: string): void => {
    const step = g.editableSteps.find((s) => s.id === stepId);
    if (step !== undefined) g.setSelectedStep(step);
  };
  const handleOrphanRemoveAll = (): void => {
    g.requestDeleteMany(
      orphanSteps.map((s) => s.id),
      { skipConfirm: true },
    );
  };

  return (
    <div
      className="relative flex h-full w-full"
      data-reduced-motion={reducedMotion ? "true" : "false"}
    >
      <ReactFlow
        nodes={g.nodes}
        edges={g.edges}
        onNodesChange={g.onNodesChange}
        onEdgesChange={g.onEdgesChange}
        onNodesDelete={g.handleNodesDelete}
        onNodeDragStop={g.handleNodeDragStop}
        onConnect={g.handleConnect}
        isValidConnection={g.isValidConnection}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        defaultEdgeOptions={{ type: "step" }}
        onMoveStart={g.handleMoveStart}
        onPaneClick={() => g.setEdgeMenu(null)}
        onEdgeClick={
          g.isCompact
            ? () => {}
            : (event, edge) => {
                event.stopPropagation();
                g.setEdgeMenu({ edge, x: event.clientX, y: event.clientY });
              }
        }
        selectionMode={SelectionMode.Partial}
        onSelectionChange={({ nodes: selectedNodes }) =>
          g.handleSelectionChange(selectedNodes)
        }
        panOnDrag
        connectionMode={ConnectionMode.Loose}
        onNodeClick={
          g.isCompact
            ? () => {}
            : (event, node) => {
                // Toolbar buttons and the kebab menu (portaled, but React
                // events still bubble here) drive their own actions; don't also
                // open the editor — its overlay would block their dialogs.
                if (isNodeToolbarOrMenuTarget(event.target)) return;
                const data = node.data as { step?: Step } | undefined;
                const step = data?.step;
                if (step != null) g.setSelectedStep(step);
              }
        }
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        snapToGrid
        snapGrid={SNAP_GRID}
        minZoom={0.1}
        maxZoom={2}
        colorMode={
          document.documentElement.getAttribute("data-theme") === "dark"
            ? "dark"
            : "light"
        }
        connectionRadius={20}
        nodesFocusable={!g.isCompact}
        edgesFocusable={!g.isCompact}
        className="bg-muted"
      >
        <Background color="hsl(var(--border))" gap={28} size={1} />
        {!g.isCompact && (
          <Panel position="top-center" className="pointer-events-none">
            <div className="flex flex-col items-center gap-2">
              <ValidationAlert
                mismatchGroups={g.combineMismatchGroups}
                isPaused={isPaused}
                onView={handleViewMismatch}
              />
              <OrphanNotice
                count={orphanSteps.length}
                firstOrphanId={firstOrphanId}
                onClickFirst={handleOrphanView}
                onRemoveAll={handleOrphanRemoveAll}
              />
            </div>
          </Panel>
        )}
        {!g.isCompact && (
          <Panel position="top-right">
            <SelectionActionBar
              selectedCount={g.selectedNodeIds.length}
              onCombine={g.handleStartCombineFromSelection}
              onOrtholog={g.handleStartOrthologTransformFromSelection}
            />
          </Panel>
        )}
        {!g.isCompact && (
          <Panel position="bottom-right">
            <CanvasControls onRelayout={g.handleRelayout} />
          </Panel>
        )}
        {!g.isCompact && (
          <Panel position="bottom-left">
            <SmartMiniMap nodeCount={g.nodes.length} />
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}
