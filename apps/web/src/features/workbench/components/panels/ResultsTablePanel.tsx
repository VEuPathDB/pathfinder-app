"use client";

import { Table } from "lucide-react";
import { ResultsTable } from "@/features/analysis/components/ResultsTable";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { useSessionStore } from "@/state/useSessionStore";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";

export function ResultsTablePanel() {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);
  const activeSet = geneSets.find((gs) => gs.id === activeSetId);

  // Result browsing requires a WDK step (strategy-backed gene set).
  const hasWdkStep = activeSet?.wdkStepId != null;
  const isDisabled = !activeSet || !hasWdkStep;

  return (
    <AnalysisPanelContainer
      panelId="results-table"
      title="Results Table"
      subtitle="Browse and sort gene records"
      icon={<Table className="h-4 w-4" />}
      disabled={isDisabled}
      disabledReason="Requires a strategy-backed gene set"
    >
      {activeSet && hasWdkStep && (
        <ResultsTable entityRef={{ type: "gene-set", id: activeSet.id }} />
      )}
    </AnalysisPanelContainer>
  );
}
