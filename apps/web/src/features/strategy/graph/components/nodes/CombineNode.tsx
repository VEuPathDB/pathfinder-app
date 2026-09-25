"use client";

import { Handle, Position } from "@xyflow/react";
import type { CombineOp } from "@pathfinder/shared";
import { operatorLabel } from "@/features/strategy/operators";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";
import { NodeShell } from "./NodeShell";
import { MiniVenn } from "./MiniVenn";
import type { StepNodeProps } from "./types";

const COMBINE_NODE_WIDTH = 168;
const COMBINE_NODE_HEIGHT = 112;

const VENN_WIDTH = 144;
const VENN_HEIGHT = 48;

export function CombineNode(props: StepNodeProps) {
  const {
    step,
    selected,
    isOrphan = false,
    showOutputHandle = false,
    showPrimaryInputHandle = false,
    showSecondaryInputHandle = false,
    enterDelayIndex,
    onOpenDetails,
    onRename,
    onDuplicate,
    onDelete,
  } = props;
  const snapshot = useStepSnapshot(step);
  const operator: CombineOp | string = step.operator ?? "";

  return (
    <NodeShell
      kind="combine"
      step={step}
      selected={selected}
      isOrphan={isOrphan}
      width={COMBINE_NODE_WIDTH}
      height={COMBINE_NODE_HEIGHT}
      snapshot={snapshot}
      enterDelayIndex={enterDelayIndex}
      onOpenDetails={onOpenDetails}
      onRename={onRename}
      onDuplicate={onDuplicate}
      onDelete={onDelete}
      handles={
        <>
          <Handle
            type="target"
            position={Position.Left}
            id="left"
            data-testid={`rf-handle-${step.id}-primary`}
            isConnectable={showPrimaryInputHandle}
            style={{ top: "30%" }}
            className={`z-10 h-3 w-3 border-2 border-card ${
              showPrimaryInputHandle
                ? "bg-foreground"
                : "pointer-events-none bg-foreground opacity-0"
            }`}
          />
          <Handle
            type="target"
            position={Position.Left}
            id="left-secondary"
            data-testid={`rf-handle-${step.id}-secondary`}
            isConnectable={showSecondaryInputHandle}
            style={{ top: "70%" }}
            className={`z-10 h-3 w-3 border-2 border-card ${
              showSecondaryInputHandle
                ? "bg-muted-foreground"
                : "pointer-events-none bg-muted-foreground opacity-0"
            }`}
          />
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
        </>
      }
    >
      {operator !== "" && (
        <div className="flex flex-col items-center gap-1">
          <MiniVenn
            operator={operator}
            width={VENN_WIDTH}
            height={VENN_HEIGHT}
            className="mx-auto"
          />
          <div
            data-testid="combine-operator-badge"
            className="inline-flex items-center rounded-sm border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-foreground"
          >
            {operatorLabel(operator)}
          </div>
        </div>
      )}
    </NodeShell>
  );
}
