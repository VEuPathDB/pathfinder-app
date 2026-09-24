"use client";

import { Handle, Position } from "@xyflow/react";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";
import { stepReason } from "@/features/strategy/graph/utils/stepTitle";
import { NodeShell } from "./NodeShell";
import type { StepNodeProps } from "./types";

const TRANSFORM_NODE_WIDTH = 184;
const TRANSFORM_NODE_HEIGHT = 80;
// A step that says why it runs its search draws one more line.
const TRANSFORM_NODE_HEIGHT_WITH_REASON = 96;

const CHEVRON_CLIP =
  "polygon(0% 0%, calc(100% - 14px) 0%, 100% 50%, calc(100% - 14px) 100%, 0% 100%)";

export function TransformNode(props: StepNodeProps) {
  const {
    step,
    selected,
    isUnsaved = false,
    isOrphan = false,
    showOutputHandle = false,
    showPrimaryInputHandle = false,
    enterDelayIndex,
    onOpenDetails,
    onRename,
    onDuplicate,
    onDelete,
  } = props;
  const snapshot = useStepSnapshot(step);

  return (
    <NodeShell
      kind="transform"
      step={step}
      selected={selected}
      isUnsaved={isUnsaved}
      isOrphan={isOrphan}
      width={TRANSFORM_NODE_WIDTH}
      height={
        stepReason(step, "transform") === ""
          ? TRANSFORM_NODE_HEIGHT
          : TRANSFORM_NODE_HEIGHT_WITH_REASON
      }
      snapshot={snapshot}
      enterDelayIndex={enterDelayIndex}
      onOpenDetails={onOpenDetails}
      onRename={onRename}
      onDuplicate={onDuplicate}
      onDelete={onDelete}
      surfaceClipPath={CHEVRON_CLIP}
      surfaceClipDataAttr="chevron-right"
      handles={
        <>
          <Handle
            type="target"
            position={Position.Left}
            id="left"
            data-testid={`rf-handle-${step.id}-primary`}
            isConnectable={showPrimaryInputHandle}
            style={{ top: "50%" }}
            className={`z-10 h-3 w-3 border-2 border-card ${
              showPrimaryInputHandle
                ? "bg-foreground"
                : "pointer-events-none bg-foreground opacity-0"
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
    />
  );
}
