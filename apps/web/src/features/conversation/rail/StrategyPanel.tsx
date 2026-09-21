"use client";

import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Bookmark, ExternalLink, RefreshCw, Workflow } from "lucide-react";

import { siteShortName, type Strategy } from "@pathfinder/shared";
import { Button } from "@/components/ui/button";
import { CompactStrategyView } from "@/features/strategy/graph/components/CompactStrategyView";
import { InsertSavedDialog } from "@/features/saved/InsertSavedDialog";
import { SaveSubstrategyDialog } from "@/features/strategy/editor/SaveSubstrategyDialog";
import { useRefreshStepCountsMutation } from "@/features/strategy/mutations/useRefreshStepCountsMutation";
import { useSaveSubstrategyMutation } from "@/features/strategy/mutations/useSaveSubstrategyMutation";
import { strategyCanvasUrl, strategyStepUrl } from "@/lib/routes";

import { RailEmptyState, RailPanelShell } from "./RailPanelShell";

interface StrategyPanelProps {
  strategy: Strategy | null;
  siteId: string;
  conversationId: string;
}

const STEP_ROUTE_RE = /\/strategy\/step\/([^/?#]+)/;

export function StrategyPanel({
  strategy,
  siteId,
  conversationId,
}: StrategyPanelProps) {
  const router = useRouter();
  const pathname = usePathname() as string | null;
  const selectedStepId =
    pathname != null ? (pathname.match(STEP_ROUTE_RE)?.[1] ?? null) : null;
  const hasSteps = strategy != null && strategy.steps.length > 0;
  const wdkUrl = strategy?.wdkUrl ?? null;

  const [saveStepId, setSaveStepId] = useState<string | null>(null);
  const [insertTargetId, setInsertTargetId] = useState<string | null>(null);
  const [insertAsRoot, setInsertAsRoot] = useState(false);

  const saveMutation = useSaveSubstrategyMutation({
    conversationId: strategy?.id ?? "",
    siteId,
    onSuccess: () => setSaveStepId(null),
  });

  const refreshCounts = useRefreshStepCountsMutation({
    conversationId: strategy?.id ?? "",
    siteId,
  });

  const openFullEditor = (): void => {
    if (strategy == null) return;
    router.push(strategyCanvasUrl(siteId, strategy.id));
  };

  const openStep = (stepId: string): void => {
    if (strategy == null) return;
    router.push(strategyStepUrl(siteId, strategy.id, stepId));
  };

  const saveTargetStep =
    saveStepId != null
      ? (strategy?.steps.find((s) => s.id === saveStepId) ?? null)
      : null;

  return (
    <RailPanelShell
      title="Strategy"
      headerActions={
        hasSteps ? (
          <div className="flex items-center gap-1">
            <Button
              data-testid="rail-strategy-refresh"
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled={refreshCounts.isPending}
              onClick={() => refreshCounts.mutate()}
              aria-label="Refresh step counts"
              title="Refresh step counts"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${refreshCounts.isPending ? "animate-spin" : ""}`}
                aria-hidden
              />
            </Button>
            {wdkUrl != null && wdkUrl !== "" && (
              <Button
                asChild
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2 text-xs"
              >
                <a
                  href={wdkUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="rail-strategy-wdk-link"
                >
                  {siteShortName(siteId)}
                  <ExternalLink className="size-3" aria-hidden />
                </a>
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={openFullEditor}
              data-testid="rail-strategy-open"
              className="h-7 gap-1 px-2 text-xs"
            >
              Open
            </Button>
          </div>
        ) : null
      }
    >
      {hasSteps ? (
        <div className="flex h-full flex-col" data-testid="rail-strategy-panel">
          <div className="min-h-0 flex-1 overflow-auto">
            <CompactStrategyView
              strategy={strategy}
              onStepClick={openStep}
              selectedStepId={selectedStepId}
              onSaveStep={setSaveStepId}
              onInsertSavedAt={setInsertTargetId}
            />
          </div>
          <StrategyFooter strategy={strategy} />
        </div>
      ) : (
        <RailEmptyState
          icon={<Workflow className="h-8 w-8" aria-hidden />}
          heading="No strategy built yet"
          description="The strategy is built here once the plan is approved, or start from one you saved."
          action={
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              onClick={() => setInsertAsRoot(true)}
              data-testid="rail-strategy-insert-saved"
            >
              <Bookmark className="size-3" aria-hidden />
              Insert saved strategy
            </Button>
          }
        />
      )}
      {insertAsRoot && (
        <InsertSavedDialog
          open
          onOpenChange={(o) => {
            if (!o) setInsertAsRoot(false);
          }}
          conversationId={conversationId}
          siteId={siteId}
          targetStepId=""
        />
      )}
      {strategy != null && (
        <>
          <SaveSubstrategyDialog
            open={saveStepId != null}
            onOpenChange={(o) => {
              if (!o) setSaveStepId(null);
            }}
            defaultName={
              saveTargetStep?.displayName ??
              saveTargetStep?.searchName ??
              "Saved strategy"
            }
            isSaving={saveMutation.isPending}
            onConfirm={(input) => {
              if (saveStepId == null) return;
              saveMutation.mutate({
                stepId: saveStepId,
                name: input.name,
                description: input.description === "" ? null : input.description,
              });
            }}
          />
          <InsertSavedDialog
            open={insertTargetId != null}
            onOpenChange={(o) => {
              if (!o) setInsertTargetId(null);
            }}
            conversationId={strategy.id}
            siteId={siteId}
            targetStepId={insertTargetId ?? ""}
          />
        </>
      )}
    </RailPanelShell>
  );
}

interface StrategyFooterProps {
  strategy: Strategy;
}

function StrategyFooter({ strategy }: StrategyFooterProps) {
  const stepCount = strategy.steps.length;
  return (
    <div
      className="border-t border-border px-3 py-2 text-[10px] text-muted-foreground"
      data-testid="rail-strategy-footer"
    >
      {stepCount} {stepCount === 1 ? "step" : "steps"}
    </div>
  );
}
