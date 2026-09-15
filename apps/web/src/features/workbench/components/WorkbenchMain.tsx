"use client";

import { formatParamValue } from "@/lib/parameters/paramValue";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { useSessionStore } from "@/state/useSessionStore";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { EmptyState } from "@/components/ui/empty-state";
import { Layers, RefreshCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useInvalidateGeneSets } from "@/features/workbench/hooks/useInvalidateGeneSets";
import { retakeGeneSet } from "../api/geneSets";
import { canRetakeGeneSet } from "./canRetakeGeneSet";
import { PublishToVdiButton } from "./PublishToVdiButton";
import { SOURCE_CONFIG } from "./geneSetSourceConfig";
import {
  EnrichmentPanel,
  DistributionsPanel,
  CustomEnrichmentPanel,
  SweepPanel,
  ResultsTablePanel,
  EnsemblePanel,
  ConfidencePanel,
  ReverseSearchPanel,
  EvaluatePanel,
  BatchPanel,
  BenchmarkPanel,
} from "./panels";

// ---------------------------------------------------------------------------
// Active set header — rich version
// ---------------------------------------------------------------------------

function RetakeButton({ geneSetId }: { geneSetId: string }) {
  const invalidateGeneSets = useInvalidateGeneSets();
  const [running, setRunning] = useState(false);

  const handleRetake = async (): Promise<void> => {
    setRunning(true);
    try {
      const set = await retakeGeneSet(geneSetId);
      void invalidateGeneSets();
      toast.success(`Re-took ${set.geneCount.toLocaleString()} genes`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Re-take failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleRetake()}
      disabled={running}
      title="Replace these genes with what the source strategy holds now"
      className="flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
    >
      <RefreshCw className={`size-3 ${running ? "animate-spin" : ""}`} aria-hidden />
      {running ? "Re-taking..." : "Re-take from strategy"}
    </button>
  );
}

function ActiveSetHeader() {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);
  const activeSet = geneSets.find((gs) => gs.id === activeSetId);

  if (!activeSet) return null;

  const colorClass = SOURCE_CONFIG[activeSet.source].badgeClass;

  return (
    <div className="mb-4 px-4 py-3 animate-fade-in">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-base font-semibold text-foreground">{activeSet.name}</h1>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground tabular-nums">
          {activeSet.geneCount.toLocaleString()} genes
        </span>
        <span
          className={`rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize ${colorClass}`}
        >
          {activeSet.source}
        </span>
        <span className="text-xs text-muted-foreground">{activeSet.siteId}</span>
        {canRetakeGeneSet(activeSet) && <RetakeButton geneSetId={activeSet.id} />}
        <PublishToVdiButton geneSet={activeSet} />
      </div>
      {activeSet.searchName != null && activeSet.searchName !== "" && (
        <p className="mt-1 text-xs text-muted-foreground">
          {activeSet.searchName}
          {activeSet.parameters != null &&
            Object.entries(activeSet.parameters)
              .slice(0, 3)
              .map(([k, v]) => ` \u00b7 ${k}: ${formatParamValue(v)}`)
              .join("")}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel list with staggered animation
// ---------------------------------------------------------------------------

export const WORKBENCH_PANELS = [
  EvaluatePanel,
  BatchPanel,
  BenchmarkPanel,
  ResultsTablePanel,
  EnrichmentPanel,
  DistributionsPanel,
  ConfidencePanel,
  EnsemblePanel,
  ReverseSearchPanel,
  CustomEnrichmentPanel,
  SweepPanel,
];

// ---------------------------------------------------------------------------
// Main content area
// ---------------------------------------------------------------------------

export function WorkbenchMain() {
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);

  if (activeSetId == null) {
    return (
      <EmptyState
        icon={<Layers className="h-10 w-10" />}
        heading="Welcome to the Workbench"
        description="Add a gene set to get started. Paste gene IDs, import from a strategy, or upload a file."
      />
    );
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Key on activeSetId so all panels remount (reset local state) on gene set switch */}
      <div key={activeSetId} className="mx-auto w-full max-w-5xl space-y-3 p-6">
        <ActiveSetHeader />
        {WORKBENCH_PANELS.map((Panel, i) => (
          <div
            key={i}
            className="animate-fade-in"
            style={{
              animationDelay: `${i * 40}ms`,
              animationFillMode: "backwards",
            }}
          >
            <Panel />
          </div>
        ))}
      </div>
    </div>
  );
}
