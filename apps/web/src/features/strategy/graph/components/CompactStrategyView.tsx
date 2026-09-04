"use client";

import type { Strategy } from "@pathfinder/shared";

import { CompactDisconnectedSection } from "@/features/strategy/graph/components/CompactDisconnectedSection";
import { CompactTreeRow } from "@/features/strategy/graph/components/CompactTree";
import { findOrphanSteps } from "@/features/strategy/graph/orphans";
import { buildStrategyTree } from "@/features/strategy/graph/utils/compactLayout";

interface CompactStrategyViewProps {
  strategy: Strategy | null;
  /** Click handler for any step row. Receives the step id. */
  onStepClick?: (stepId: string) => void;
  /** Step id currently focused by the URL / editor sheet. */
  selectedStepId?: string | null;
  /** Optional row-level actions surfaced via a kebab menu. */
  onSaveStep?: (stepId: string) => void;
  onInsertSavedAt?: (stepId: string) => void;
}

export function CompactStrategyView({
  strategy,
  onStepClick,
  selectedStepId = null,
  onSaveStep,
  onInsertSavedAt,
}: CompactStrategyViewProps) {
  if (strategy == null) return null;

  const tree =
    strategy.steps.length === 0 ||
    strategy.rootStepId == null ||
    strategy.rootStepId === ""
      ? []
      : buildStrategyTree(strategy.steps, strategy.rootStepId);

  const orphans = findOrphanSteps(strategy.steps, strategy.rootStepId ?? null);

  if (tree.length === 0 && orphans.length === 0) {
    return (
      <div className="px-3 py-3 text-xs text-muted-foreground">
        Building strategy ({strategy.steps.length} steps)...
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      {tree.length > 0 && (
        <ol data-testid="compact-strategy-view" className="flex flex-col gap-1">
          {tree.map((node) => (
            <CompactTreeRow
              key={node.step.id}
              node={node}
              allSteps={strategy.steps}
              selectedStepId={selectedStepId}
              {...(onStepClick !== undefined && { onStepClick })}
              {...(onSaveStep !== undefined && { onSaveStep })}
              {...(onInsertSavedAt !== undefined && { onInsertSavedAt })}
            />
          ))}
        </ol>
      )}
      {orphans.length > 0 && (
        <CompactDisconnectedSection
          strategy={strategy}
          orphans={orphans}
          selectedStepId={selectedStepId}
          {...(onStepClick !== undefined && { onStepClick })}
        />
      )}
    </div>
  );
}
