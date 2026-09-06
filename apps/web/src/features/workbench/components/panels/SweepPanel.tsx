"use client";

import { TrendingUp } from "lucide-react";
import { ThresholdSweepSection } from "@/features/workbench/analysis";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";

/**
 * SweepPanel wraps the ThresholdSweepSection analysis component.
 *
 * The sweep requires a full Experiment object (with config, metrics, etc.)
 * to know which parameters are sweepable and what the baseline is.
 *
 * It reads the last completed experiment from the workbench store and only
 * enables when the experiment belongs to the currently active gene set.
 */
export function SweepPanel() {
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);
  const lastExperiment = useWorkbenchStore((s) => s.lastExperiment);
  const lastExperimentSetId = useWorkbenchStore((s) => s.lastExperimentSetId);

  // Only enable if we have an experiment for the current active set
  const experiment = lastExperimentSetId === activeSetId ? lastExperiment : null;
  const isDisabled = experiment === null;

  return (
    <AnalysisPanelContainer
      panelId="sweep"
      title="Parameter Sweep"
      subtitle="Sweep a parameter to visualize sensitivity/specificity trade-offs"
      icon={<TrendingUp className="h-4 w-4" />}
      disabled={isDisabled}
      disabledReason="Requires a completed evaluation first"
    >
      {experiment && <ThresholdSweepSection experiment={experiment} />}
    </AnalysisPanelContainer>
  );
}
