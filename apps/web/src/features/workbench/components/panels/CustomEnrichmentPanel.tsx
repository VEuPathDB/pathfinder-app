"use client";

import { FlaskConical } from "lucide-react";
import { CustomEnrichmentSection } from "@/features/workbench/analysis";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";

export function CustomEnrichmentPanel() {
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);
  const lastExperiment = useWorkbenchStore((s) => s.lastExperiment);
  const lastExperimentSetId = useWorkbenchStore((s) => s.lastExperimentSetId);

  const experiment = lastExperimentSetId === activeSetId ? lastExperiment : null;
  const isDisabled = !experiment;

  return (
    <AnalysisPanelContainer
      panelId="custom-enrichment"
      title="Custom Enrichment"
      subtitle="Test enrichment against your own gene sets using Fisher's exact test"
      icon={<FlaskConical className="h-4 w-4" />}
      disabled={isDisabled}
      disabledReason="Requires a completed evaluation first"
    >
      {experiment && <CustomEnrichmentSection experimentId={experiment.id} />}
    </AnalysisPanelContainer>
  );
}
