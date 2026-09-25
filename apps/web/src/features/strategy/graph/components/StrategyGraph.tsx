"use client";

import { ReactFlowProvider } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useState } from "react";
import type { Strategy } from "@pathfinder/shared";
import { Editor } from "@/features/strategy/editor/Editor";
import {
  CanvasTopbar,
  type SyncState,
} from "@/features/strategy/graph/components/CanvasTopbar";
import { EmptyState } from "@/features/strategy/graph/components/EmptyState";
import { EdgeContextMenu } from "@/features/strategy/graph/components/EdgeContextMenu";
import { GraphActionConfirm } from "@/features/strategy/graph/components/GraphActionConfirm";
import { OrthologSheet } from "@/features/strategy/graph/components/OrthologSheet";
import { QuickSwitcher } from "@/features/strategy/graph/components/QuickSwitcher";
import { ShortcutsOverlay } from "@/features/strategy/graph/components/ShortcutsOverlay";
import { StrategyGraphLayout } from "@/features/strategy/graph/components/StrategyGraphLayout";
import { SyncProgressBar } from "@/features/strategy/graph/components/SyncProgressBar";
import { useStrategyGraph } from "@/features/strategy/graph/hooks/useStrategyGraph";
import { useQuickSwitcher } from "@/features/strategy/graph/hooks/useQuickSwitcher";
import { useStrategyKeyboardShortcuts } from "@/features/strategy/graph/hooks/useStrategyKeyboardShortcuts";
import { useRetryLastPush } from "@/features/strategy/mutations";
import { operatorPatch } from "@/features/strategy/operators";
import {
  StrategyGraphProvider,
  useStrategyGraphCtx,
  type StrategyGraphContextValue,
} from "@/features/strategy/graph/StrategyGraphContext";

interface StrategyGraphProps {
  strategy: Strategy | null;
  siteId: string;
  conversationId: string;
  showTopbar?: boolean;
  focusStepId?: string | null;
}

export function StrategyGraph(props: StrategyGraphProps) {
  return (
    <ReactFlowProvider>
      <StrategyGraphInner {...props} />
    </ReactFlowProvider>
  );
}

function StrategyGraphInner({
  strategy,
  siteId,
  conversationId,
  showTopbar = true,
  focusStepId = null,
}: StrategyGraphProps) {
  const g = useStrategyGraph({ strategy, siteId });

  // Render-time focus sync: when the URL provides a step id, open the editor
  // sheet on it. Re-runs only when the requested id changes.
  const [appliedFocusStepId, setAppliedFocusStepId] = useState<string | null>(null);
  if (focusStepId !== appliedFocusStepId) {
    setAppliedFocusStepId(focusStepId);
    if (focusStepId === null) {
      g.setSelectedStep(null);
    } else {
      const target = (strategy?.steps ?? []).find((s) => s.id === focusStepId);
      if (target !== undefined) g.setSelectedStep(target);
    }
  }

  if (strategy == null || strategy.steps.length === 0) {
    return (
      <EmptyState
        siteId={siteId}
        recordType={strategy?.recordType ?? null}
        conversationId={conversationId}
      />
    );
  }

  const ctxValue: StrategyGraphContextValue = { ...g, strategy, siteId };
  const syncState = computeSyncState(g.syncStatus);

  return (
    <StrategyGraphProvider value={ctxValue}>
      <StrategyGraphChrome
        strategy={strategy}
        siteId={siteId}
        showTopbar={showTopbar}
        syncState={syncState}
      />
    </StrategyGraphProvider>
  );
}

interface StrategyGraphChromeProps {
  strategy: Strategy;
  siteId: string;
  showTopbar: boolean;
  syncState: SyncState;
}

function StrategyGraphChrome({
  strategy,
  siteId,
  showTopbar,
  syncState,
}: StrategyGraphChromeProps) {
  const g = useStrategyGraphCtx();
  const quickSwitcher = useQuickSwitcher();
  const retryLastPush = useRetryLastPush(strategy.id);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  useStrategyKeyboardShortcuts({
    onOpenQuickSwitcher: () => quickSwitcher.setOpen(true),
    onToggleShortcutsOverlay: () => setShortcutsOpen((prev) => !prev),
  });

  return (
    <div className="relative flex h-full w-full flex-col">
      <SyncProgressBar active={syncState === "saving"} />
      {showTopbar && (
        <CanvasTopbar
          strategy={strategy}
          conversationId={strategy.id}
          syncState={syncState}
          onRetry={retryLastPush}
        />
      )}
      <div className="relative flex-1">
        <StrategyGraphLayout />
      </div>
      {g.edgeMenu && (
        <EdgeContextMenu
          edge={g.edgeMenu.edge}
          x={g.edgeMenu.x}
          y={g.edgeMenu.y}
          steps={g.editableSteps}
          onDeleteEdge={(edge) => {
            g.handleDeleteEdge(edge);
            g.setEdgeMenu(null);
          }}
          onChangeOperator={(stepId, operator) => {
            g.updateStep(stepId, operatorPatch(operator));
            g.setEdgeMenu(null);
          }}
          onClose={() => g.setEdgeMenu(null)}
        />
      )}
      {g.orthologTargetId !== null && (
        <OrthologSheet
          open
          onOpenChange={(next) => {
            if (!next) g.setOrthologTargetId(null);
          }}
          siteId={siteId}
          recordType={strategy.recordType ?? "gene"}
          onChoose={g.handleOrthologChoose}
        />
      )}
      <Editor
        step={g.selectedStep}
        isOpen={g.selectedStep != null}
        onOpenChange={(open) => {
          if (!open) g.setSelectedStep(null);
        }}
        siteId={siteId}
        recordType={strategy.recordType ?? null}
        conversationId={strategy.id}
      />
      <QuickSwitcher
        open={quickSwitcher.open}
        onOpenChange={quickSwitcher.setOpen}
        strategy={strategy}
      />
      <ShortcutsOverlay open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
      {g.deleteDialogProps !== null && <GraphActionConfirm {...g.deleteDialogProps} />}
    </div>
  );
}

function computeSyncState(status: "idle" | "syncing" | "error"): SyncState {
  if (status === "syncing") return "saving";
  if (status === "error") return "error";
  return "idle";
}
