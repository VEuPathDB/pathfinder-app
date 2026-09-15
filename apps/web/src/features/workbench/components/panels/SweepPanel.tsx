"use client";

import { TrendingUp } from "lucide-react";
import { ThresholdSweepSection } from "@/features/workbench/analysis";
import { useActiveSetExperiment } from "@/features/workbench/hooks/useActiveSetExperiment";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";

/**
 * SweepPanel wraps the ThresholdSweepSection analysis component.
 *
 * The sweep requires a full Experiment object (with config, metrics, etc.)
 * to know which parameters are sweepable and what the baseline is.
 */
export function SweepPanel() {
  const experiment = useActiveSetExperiment();

  return (
    <AnalysisPanelContainer
      panelId="sweep"
      title="Parameter Sweep"
      subtitle="Sweep a parameter to visualize sensitivity/specificity trade-offs"
      icon={<TrendingUp className="h-4 w-4" />}
      disabled={experiment === null}
      disabledReason="Requires a completed evaluation first"
    >
      {experiment && <ThresholdSweepSection experiment={experiment} />}
    </AnalysisPanelContainer>
  );
}
