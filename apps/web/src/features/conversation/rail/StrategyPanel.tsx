"use client";

import { usePathname } from "next/navigation";
import { Bookmark, Check, CircleAlert, RefreshCw, Workflow } from "lucide-react";

import { siteShortName, type EvidenceCard, type Strategy } from "@strategist/shared";
import { Button } from "@/components/ui/button";
import { CompactStrategyView } from "@/features/strategy/graph/components/CompactStrategyView";
import { AnimatedCount } from "@/lib/components/AnimatedCount";
import { OpenInSiteLink } from "@/lib/components/OpenInSiteLink";
import { countNoun } from "@/lib/utils/countNoun";
import { countOf } from "@/lib/utils/countOf";
import { cn } from "@/lib/utils/cn";
import { useStepSnapshot } from "@/state/strategy/useStepSnapshot";

import { RailEmptyState, RailPanelShell } from "./RailPanelShell";
import type { RailSource } from "./railSource";

export interface StrategyCheck {
  card: EvidenceCard;
  superseded: boolean;
}

interface StrategyPanelProps {
  source: RailSource;
  check: StrategyCheck | null;
}

const STEP_ROUTE_RE = /\/strategy\/step\/([^/?#]+)/;

export function StrategyPanel({ source, check }: StrategyPanelProps) {
  const pathname = usePathname() as string | null;
  const selectedStepId =
    pathname != null ? (pathname.match(STEP_ROUTE_RE)?.[1] ?? null) : null;
  const { strategy, siteId, owner } = source;
  const actions = owner?.strategy ?? null;
  const hasSteps = strategy != null && strategy.steps.length > 0;
  const wdkUrl = strategy?.wdkUrl ?? null;

  return (
    <RailPanelShell
      title="Strategy"
      headerActions={
        hasSteps && actions !== null ? (
          <div className="flex items-center gap-1">
            <Button
              data-testid="rail-strategy-refresh"
              type="button"
              variant="ghost"
              size="icon-sm"
              disabled={actions.refresh.pending}
              onClick={actions.refresh.run}
              aria-label="Refresh step counts"
              title="Refresh step counts"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${actions.refresh.pending ? "animate-spin" : ""}`}
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
            {actions !== null && (
              <div className="flex flex-wrap items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={actions.openEditor}
                  data-testid="rail-strategy-open"
                  className="h-7 px-2.5 text-xs transition-transform active:scale-[0.98]"
                >
                  Open editor
                </Button>
                {wdkUrl != null && wdkUrl !== "" && (
                  <OpenInSiteLink href={wdkUrl} siteId={siteId} opens="strategy" />
                )}
              </div>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <CompactStrategyView
              strategy={strategy}
              selectedStepId={selectedStepId}
              privateStepIds={new Set(Object.keys(source.privateInputs))}
              {...(actions !== null && {
                onStepClick: actions.openStep,
                onSaveStep: actions.saveStep,
                onInsertSavedAt: actions.insertSavedAt,
                onRemoveOrphans: actions.removeSteps,
              })}
            />
          </div>
        </div>
      ) : (
        <RailEmptyState
          icon={<Workflow className="h-8 w-8" aria-hidden />}
          heading="No strategy built yet"
          description={
            actions === null
              ? "The strategy is built here once the plan is approved."
              : "The strategy is built here once the plan is approved, or start from one you saved."
          }
          {...(actions !== null && {
            action: (
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1 px-2 text-xs"
                onClick={actions.insertSavedAsRoot}
                data-testid="rail-strategy-insert-saved"
              >
                <Bookmark className="size-3" aria-hidden />
                Insert saved strategy
              </Button>
            ),
          })}
        />
      )}
      {actions?.dialogs}
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
