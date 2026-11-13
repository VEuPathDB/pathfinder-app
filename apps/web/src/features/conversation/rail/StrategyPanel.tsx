"use client";

import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Bookmark, Check, CircleAlert, RefreshCw, Workflow } from "lucide-react";

import { siteShortName, type EvidenceCard, type Strategy } from "@strategist/shared";
import { Button } from "@/components/ui/button";
import { CompactStrategyView } from "@/features/strategy/graph/components/CompactStrategyView";
import { InsertSavedDialog } from "@/features/saved/InsertSavedDialog";
import { beginConversation } from "@/features/conversation/api/beginConversation";
import { SaveSubstrategyDialog } from "@/features/strategy/editor/SaveSubstrategyDialog";
import { useRefreshStepCountsMutation } from "@/features/strategy/mutations/useRefreshStepCountsMutation";
import { useSaveSubstrategyMutation } from "@/features/strategy/mutations/useSaveSubstrategyMutation";
import { AnimatedCount } from "@/lib/components/AnimatedCount";
import { OpenInSiteLink } from "@/lib/components/OpenInSiteLink";
import { countNoun } from "@/lib/utils/countNoun";
import { countOf } from "@/lib/utils/countOf";
import { cn } from "@/lib/utils/cn";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";
import { strategyCanvasUrl, strategyStepUrl } from "@/lib/routes";

import { RailEmptyState, RailPanelShell } from "./RailPanelShell";

export interface StrategyCheck {
  card: EvidenceCard;
  superseded: boolean;
}

interface StrategyPanelProps {
  strategy: Strategy | null;
  siteId: string;
  conversationId: string;
  check: StrategyCheck | null;
}

const STEP_ROUTE_RE = /\/strategy\/step\/([^/?#]+)/;

export function StrategyPanel({
  strategy,
  siteId,
  conversationId,
  check,
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
    router.push(strategyCanvasUrl(strategy.id));
  };

  const openStep = (stepId: string): void => {
    if (strategy == null) return;
    router.push(strategyStepUrl(strategy.id, stepId));
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
          </div>
        ) : null
      }
    >
      {hasSteps ? (
        <div className="flex h-full flex-col" data-testid="rail-strategy-panel">
          <div className="flex flex-col gap-2.5 border-b border-border px-4 py-4">
            <Headline strategy={strategy} />
            <CheckLine check={check} siteId={siteId} />
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={openFullEditor}
                data-testid="rail-strategy-open"
                className="h-7 px-2.5 text-xs transition-transform active:scale-[0.98]"
              >
                Open editor
              </Button>
              {wdkUrl != null && wdkUrl !== "" && (
                <OpenInSiteLink href={wdkUrl} siteId={siteId} opens="strategy" />
              )}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <CompactStrategyView
              strategy={strategy}
              onStepClick={openStep}
              selectedStepId={selectedStepId}
              onSaveStep={setSaveStepId}
              onInsertSavedAt={setInsertTargetId}
            />
          </div>
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
          beginThread={() => beginConversation(conversationId, { siteId })}
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
            beginThread={() => beginConversation(strategy.id, { siteId })}
          />
        </>
      )}
    </RailPanelShell>
  );
}

function Headline({ strategy }: { strategy: Strategy }) {
  const root = strategy.steps.find((step) => step.id === strategy.rootStepId) ?? null;
  const size = useStepSnapshot(root).estimatedSize;
  return (
    <p data-testid="strategy-headline" className="flex items-baseline gap-1.5">
      {typeof size === "number" ? (
        <AnimatedCount
          value={size}
          className="text-2xl font-semibold tracking-tight tabular-nums text-foreground"
        />
      ) : (
        <span className="text-2xl font-semibold text-muted-foreground">...</span>
      )}
      <span className="text-sm text-muted-foreground">
        {countNoun(
          root?.recordType ?? strategy.recordType,
          typeof size === "number" ? size : 2,
        )}
      </span>
    </p>
  );
}

function checkWords(
  check: StrategyCheck,
  site: string,
): { text: string; good: boolean } {
  if (check.superseded) return { text: "Changed since the last check", good: false };
  if (check.card.siteRead !== "read") {
    return { text: `${site} did not answer the check`, good: false };
  }
  const drifted = check.card.steps.filter((step) => step.drifted).length;
  if (drifted > 0) {
    return {
      text: `${countOf(drifted, "count", "counts")} changed on ${site} since the build`,
      good: false,
    };
  }
  return { text: `Checked: every count matches ${site}`, good: true };
}

function CheckLine({ check, siteId }: { check: StrategyCheck | null; siteId: string }) {
  if (check === null) return null;
  const { text, good } = checkWords(check, siteShortName(siteId));
  const Icon = good ? Check : CircleAlert;
  return (
    <p
      data-testid="strategy-check"
      className={cn(
        "flex items-center gap-1.5 text-xs",
        good ? "text-success" : "text-muted-foreground",
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {text}
    </p>
  );
}
