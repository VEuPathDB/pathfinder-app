"use client";

import { BarChart3 } from "lucide-react";
import { DistributionExplorer } from "@/features/workbench/analysis";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { useSessionStore } from "@/state/useSessionStore";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";

export function DistributionsPanel() {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);
  const activeSet = geneSets.find((gs) => gs.id === activeSetId);

  // Distribution explorer requires a WDK step (strategy-backed gene set).
  const hasWdkStep = activeSet?.wdkStepId != null;
  const isDisabled = !activeSet || !hasWdkStep;

  return (
    <AnalysisPanelContainer
      panelId="distributions"
      title="Distribution Explorer"
      subtitle="Explore attribute distributions across the gene set"
      icon={<BarChart3 className="h-4 w-4" />}
      disabled={isDisabled}
      disabledReason="Requires a strategy-backed gene set"
    >
      {activeSet && hasWdkStep && (
        <DistributionExplorer entityRef={{ type: "gene-set", id: activeSet.id }} />
      )}
    </AnalysisPanelContainer>
  );
}
