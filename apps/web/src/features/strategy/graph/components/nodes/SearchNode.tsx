"use client";

import { Handle, Position } from "@xyflow/react";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";
import { NodeShell } from "./NodeShell";
import type { StepNodeProps } from "./types";

const SEARCH_NODE_WIDTH = 168;
const SEARCH_NODE_HEIGHT = 64;

export function SearchNode(props: StepNodeProps) {
  const {
    step,
    selected,
    isUnsaved = false,
    isOrphan = false,
    showOutputHandle = false,
    enterDelayIndex,
    onOpenDetails,
    onRename,
    onDuplicate,
    onDelete,
  } = props;
  const snapshot = useStepSnapshot(step);

  return (
    <NodeShell
      kind="search"
      step={step}
      selected={selected}
      isUnsaved={isUnsaved}
      isOrphan={isOrphan}
      width={SEARCH_NODE_WIDTH}
      height={SEARCH_NODE_HEIGHT}
      snapshot={snapshot}
      enterDelayIndex={enterDelayIndex}
      onOpenDetails={onOpenDetails}
      onRename={onRename}
      onDuplicate={onDuplicate}
      onDelete={onDelete}
      handles={
        <Handle
          type="source"
          position={Position.Right}
          id="right"
          data-testid={`rf-handle-${step.id}-output`}
          isConnectable={showOutputHandle}
          style={{ top: "50%" }}
          className={`z-10 h-3 w-3 border-2 border-input ${
            showOutputHandle ? "bg-card" : "pointer-events-none bg-card opacity-0"
          }`}
        />
      }
    />
  );
}
