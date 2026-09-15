"use client";

import { FlaskConical } from "lucide-react";
import { CustomEnrichmentSection } from "@/features/workbench/analysis";
import { useActiveSetExperiment } from "@/features/workbench/hooks/useActiveSetExperiment";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";

export function CustomEnrichmentPanel() {
  const experiment = useActiveSetExperiment();

  return (
    <AnalysisPanelContainer
      panelId="custom-enrichment"
      title="Custom Enrichment"
      subtitle="Test enrichment against your own gene sets using Fisher's exact test"
      icon={<FlaskConical className="h-4 w-4" />}
      disabled={experiment === null}
      disabledReason="Requires a completed evaluation first"
    >
      {experiment && <CustomEnrichmentSection experimentId={experiment.id} />}
    </AnalysisPanelContainer>
  );
}
