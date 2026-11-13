"use client";

import type { Step } from "@strategist/shared";
import { Bookmark } from "lucide-react";

import {
  CompactStepRow,
  type RowActions,
} from "@/features/strategy/graph/components/CompactRows";
import type { TreeNode } from "@/features/strategy/graph/utils/compactLayout";

interface TreeRowProps extends RowActions {
  node: TreeNode;
  allSteps: Step[];
}

/** One step, and indented beneath it the steps that feed it. */
export function CompactTreeRow({
  node,
  allSteps,
  onStepClick,
  selectedStepId = null,
  onSaveStep,
  onInsertSavedAt,
}: TreeRowProps) {
  const savedName =
    node.step.expandedStrategyId != null && node.step.expandedName != null
      ? node.step.expandedName
      : null;
  return (
    <li>
      <CompactStepRow
        step={node.step}
        selectedStepId={selectedStepId}
        {...(onStepClick !== undefined && { onStepClick })}
        {...(onSaveStep !== undefined && { onSaveStep })}
        {...(onInsertSavedAt !== undefined && { onInsertSavedAt })}
      />
      {node.children.length > 0 && (
        <ChildList
          node={node}
          allSteps={allSteps}
          selectedStepId={selectedStepId}
          savedName={savedName}
          {...(onStepClick !== undefined && { onStepClick })}
          {...(onSaveStep !== undefined && { onSaveStep })}
          {...(onInsertSavedAt !== undefined && { onInsertSavedAt })}
        />
      )}
    </li>
  );
}

function ChildList({
  node,
  allSteps,
  onStepClick,
  selectedStepId = null,
  savedName,
  onSaveStep,
  onInsertSavedAt,
}: TreeRowProps & { savedName: string | null }) {
  const list = (
    <ol
      data-testid={`compact-children-${node.step.id}`}
      className="flex flex-col gap-0.5 border-l border-border/60 pl-1.5"
    >
      {node.children.map((child) => (
        <CompactTreeRow
          key={child.step.id}
          node={child}
          allSteps={allSteps}
          selectedStepId={selectedStepId}
          {...(onStepClick !== undefined && { onStepClick })}
          {...(onSaveStep !== undefined && { onSaveStep })}
          {...(onInsertSavedAt !== undefined && { onInsertSavedAt })}
        />
      ))}
    </ol>
  );

  if (savedName == null) {
    return <div className="ml-1.5 mt-0.5">{list}</div>;
  }
  return (
    <section
      data-testid="saved-substrategy-container"
      className="ml-1.5 mt-0.5 rounded-md border border-dashed border-primary/40 bg-primary/5 p-1.5"
    >
      <header className="mb-1 flex items-center gap-2 px-1 text-xs font-medium text-primary/80">
        <Bookmark className="size-3" aria-hidden />
        <span className="truncate font-semibold">{savedName}</span>
      </header>
      {list}
    </section>
  );
}
