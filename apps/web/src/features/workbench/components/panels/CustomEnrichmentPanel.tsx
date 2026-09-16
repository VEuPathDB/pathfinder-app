"use client";

import { FlaskConical } from "lucide-react";
import { CustomEnrichmentSection } from "@/features/workbench/analysis";
import { useActiveSetEvaluation } from "@/features/workbench/hooks/useActiveSetEvaluation";
import { evaluationBlock } from "../setEvaluation";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";

export function CustomEnrichmentPanel() {
  const evaluation = useActiveSetEvaluation();
  const blocked = evaluationBlock(evaluation);

  return (
    <AnalysisPanelContainer
      panelId="custom-enrichment"
      title="Custom Enrichment"
      subtitle="Test enrichment against your own gene sets using Fisher's exact test"
      icon={<FlaskConical className="h-4 w-4" />}
      disabled={blocked !== null}
      disabledReason={blocked ?? ""}
    >
      {blocked === null && evaluation !== null && (
        <CustomEnrichmentSection experimentId={evaluation.experiment.id} />
      )}
    </AnalysisPanelContainer>
  );
}
