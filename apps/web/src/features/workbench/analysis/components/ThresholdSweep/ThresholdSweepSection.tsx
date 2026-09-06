import type { Experiment } from "@pathfinder/shared";
import { Loader2 } from "lucide-react";
import { useSweepState } from "./useSweepState";
import { SweepSetup } from "./SweepSetup";
import { SweepChart } from "./SweepChart";
import { SweepSummary } from "./SweepSummary";
import { SweepTable } from "./SweepTable";

interface ThresholdSweepSectionProps {
  experiment: Experiment;
}

export function ThresholdSweepSection({ experiment }: ThresholdSweepSectionProps) {
  const state = useSweepState(experiment);

  if (state.specsLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading parameter specifications...
      </div>
    );
  }

  if (state.sweepableParams.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-muted/30 px-5 py-8 text-center text-sm text-muted-foreground">
        No sweepable parameters detected in this experiment&apos;s configuration.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SweepSetup
        sweepableParams={state.sweepableParams}
        selectedParam={state.selectedParam}
        paramName={state.paramName}
        minVal={state.minVal}
        maxVal={state.maxVal}
        steps={state.steps}
        selectedValues={state.selectedValues}
        loading={state.loading}
        error={state.error}
        completedCount={state.completedCount}
        totalCount={state.totalCount}
        canRun={state.canRun}
        formatValue={state.formatValue}
        onMinChange={state.setMinVal}
        onMaxChange={state.setMaxVal}
        onStepsChange={state.setSteps}
        onSelectedValuesChange={state.setSelectedValues}
        onParamChange={state.handleParamChange}
        onRun={() => {
          void state.handleRun();
        }}
        onCancel={state.handleCancel}
      />

      {state.validPoints.length >= 2 && (
        <SweepChart
          points={state.validPoints}
          parameter={state.finalResult?.parameter ?? state.paramName}
          sweepType={state.activeSweepType}
          formatValue={state.formatValue}
          isStreaming={state.loading}
        />
      )}

      {state.validPoints.length >= 2 && !state.loading && state.finalResult && (
        <SweepSummary
          points={state.validPoints}
          parameter={state.finalResult.parameter}
          sweepType={state.activeSweepType}
          formatValue={state.formatValue}
          {...(state.selectedParam != null
            ? { currentValue: state.selectedParam.currentValue }
            : {})}
          failedCount={state.failedPoints.length}
        />
      )}

      {state.validPoints.length > 0 && (
        <SweepTable
          points={state.validPoints}
          parameter={state.finalResult?.parameter ?? state.paramName}
          formatValue={state.formatValue}
        />
      )}
    </div>
  );
}
