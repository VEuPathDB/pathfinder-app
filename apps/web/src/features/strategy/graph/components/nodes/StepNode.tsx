"use client";

import type { Node, NodeProps } from "@xyflow/react";
import { inferStepKind } from "@/features/strategy/graph";
import { SearchNode } from "./SearchNode";
import { CombineNode } from "./CombineNode";
import { TransformNode } from "./TransformNode";
import type { StepNodeData, StepNodeProps } from "./types";

export type { StepNodeData } from "./types";

export function StepNode({ data, selected }: NodeProps<Node<StepNodeData>>) {
  const props: StepNodeProps = {
    step: data.step,
    selected,
    isUnsaved: data.isUnsaved,
    isOrphan: data.isOrphan,
    showOutputHandle: data.showOutputHandle,
    showPrimaryInputHandle: data.showPrimaryInputHandle,
    showSecondaryInputHandle: data.showSecondaryInputHandle,
    enterDelayIndex: data.enterDelayIndex,
    onOpenDetails: data.onOpenDetails,
    onRename: data.onRename,
    onDuplicate: data.onDuplicate,
    onDelete: data.onDelete,
  };
  const kind = inferStepKind(data.step);

  if (kind === "combine") return <CombineNode {...props} />;
  if (kind === "transform") return <TransformNode {...props} />;
  return <SearchNode {...props} />;
}
