"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import { useUnmount } from "usehooks-ts";
import { Loader2, Play, Target } from "lucide-react";

import type { Experiment, EnrichmentAnalysisType } from "@pathfinder/shared";
import {
  ConfusionMatrixSection,
  CrossValidationSection,
  EnrichmentSection,
  GeneListsSection,
  MetricsOverview,
  RobustnessSection,
} from "@/features/workbench/analysis";
import { createExperimentStream } from "@/features/workbench/api";
import type { ExperimentRunConfig } from "@/features/workbench/api/streaming";
import { Button } from "@/components/ui/button";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { queryKeyPrefixes } from "@/lib/query/keys";
import { useSessionStore } from "@/state/useSessionStore";
import { useWorkbenchStore, type PanelId } from "@/state/useWorkbenchStore";

import { CONTROLS_PARAM_NAME, CONTROLS_SEARCH_NAME } from "../../constants";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { ControlSetQuickPick } from "../ControlSetQuickPick";
import { GeneChipInput } from "../GeneChipInput";
import { SaveControlSetForm } from "../SaveControlSetForm";

const PANEL_ID: PanelId = "evaluate";

/**
 * Run a full experiment evaluating the active gene set against positive and
 * negative controls. Streams typed progress via `createExperimentStream` and
 * renders the rich analysis viz (metrics, confusion matrix, CV, enrichment,
 * robustness) on completion.
 */
export function EvaluatePanel() {
  const queryClient = useQueryClient();
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);
  const {
    activeSetId,
    positiveControls,
    negativeControls,
    setPositiveControls,
    setNegativeControls,
    setLastExperiment,
  } = useWorkbenchStore(
    useShallow((s) => ({
      activeSetId: s.activeSetId,
      positiveControls: s.positiveControls,
      negativeControls: s.negativeControls,
      setPositiveControls: s.setPositiveControls,
      setNegativeControls: s.setNegativeControls,
      setLastExperiment: s.setLastExperiment,
    })),
  );
  const activeSet = geneSets.find((gs) => gs.id === activeSetId);

  const [enableCV, setEnableCV] = useState(false);
  const [kFolds, setKFolds] = useState(5);
  const [enrichmentTypes, setEnrichmentTypes] = useState<EnrichmentAnalysisType[]>([]);
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useUnmount(() => abortRef.current?.abort());

  const strategyBacked =
    activeSet?.searchName != null &&
    activeSet.searchName !== "" &&
    activeSet.parameters != null;
  const hasSearchContext = Boolean(
    activeSet != null && (activeSet.geneIds.length > 0 || strategyBacked),
  );

  const handleRun = async () => {
    if (!activeSet) return;
    if (positiveControls.length === 0) {
      setError("At least one positive control gene ID is required.");
      return;
    }
    setLoading(true);
    setError(null);
    setExperiment(null);
    setProgressText("");

    const controller = new AbortController();
    abortRef.current = controller;

    const config = {
      siteId: activeSet.siteId,
      recordType: activeSet.recordType ?? "gene",
      searchName: activeSet.searchName ?? "",
      parameters: activeSet.parameters ?? {},
      positiveControls,
      negativeControls,
      controlsSearchName: CONTROLS_SEARCH_NAME,
      controlsParamName: CONTROLS_PARAM_NAME,
      enableCrossValidation: enableCV,
      kFolds,
      targetGeneIds: strategyBacked ? undefined : activeSet.geneIds,
      enrichmentTypes,
      name: `${activeSet.name} (evaluation)`,
    } satisfies ExperimentRunConfig;

    try {
      for await (const event of createExperimentStream(config, {
        signal: controller.signal,
      })) {
        if (event.type === "experiment_progress") {
          const raw = event.data;
          const phase = typeof raw["phase"] === "string" ? raw["phase"] : undefined;
          if (phase !== undefined) setProgressText(phase);
        } else if (event.type === "experiment_complete") {
          setExperiment(event.experiment);
          setLastExperiment(event.experiment, activeSetId ?? null);
          void queryClient.invalidateQueries({
            queryKey: queryKeyPrefixes.experiments,
          });
        } else if (event.type === "experiment_error") {
          setError(event.error);
        } else {
          // experiment_end — terminal; loop exits after drain.
        }
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(err instanceof Error ? err.message : "Experiment failed");
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  if (!activeSet) return null;

  const metrics = experiment?.metrics ?? null;
  const robustness = experiment?.robustness ?? null;
  const confusionMatrix = experiment?.metrics?.confusionMatrix ?? null;
  const crossValidation = experiment?.crossValidation ?? null;
  const enrichmentResults = experiment?.enrichmentResults ?? [];

  return (
    <AnalysisPanelContainer
      panelId={PANEL_ID}
      title="Evaluate"
      subtitle="Run a full experiment against positive/negative controls"
      icon={<Target className="h-5 w-5" />}
    >
      <div className="space-y-4">
        <ControlSetQuickPick
          siteId={activeSet.siteId}
          onSelect={(pos, neg) => {
            setPositiveControls(pos);
            setNegativeControls(neg);
          }}
        />

        <GeneChipInput
          siteId={activeSet.siteId}
          value={positiveControls}
          onChange={setPositiveControls}
          label="Positive controls"
          required
          tint="positive"
        />

        <GeneChipInput
          siteId={activeSet.siteId}
          value={negativeControls}
          onChange={setNegativeControls}
          label="Negative controls (optional)"
          tint="negative"
        />

        <SaveControlSetForm
          siteId={activeSet.siteId}
          positiveIds={positiveControls}
          negativeIds={negativeControls}
          {...(activeSet.recordType != null
            ? { recordType: activeSet.recordType }
            : {})}
        />

        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={enableCV}
              onChange={(e) => setEnableCV(e.target.checked)}
            />
            Cross-validation
          </label>
          {enableCV && (
            <label className="flex items-center gap-2">
              k folds:
              <input
                type="number"
                min={2}
                max={10}
                value={kFolds}
                onChange={(e) => setKFolds(Number(e.target.value))}
                className="w-16 rounded border border-input bg-background px-2 py-1"
              />
            </label>
          )}
          <EnrichmentToggle value={enrichmentTypes} onChange={setEnrichmentTypes} />
        </div>

        <Button
          onClick={() => void handleRun()}
          disabled={loading || !hasSearchContext || positiveControls.length === 0}
          className="gap-2"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {loading ? "Running..." : "Run evaluation"}
        </Button>

        {loading && progressText !== "" && (
          <div className="text-xs text-muted-foreground">Phase: {progressText}</div>
        )}

        {error !== null && error !== "" && (
          <div
            data-testid="evaluate-error"
            className="rounded border border-destructive/40 bg-destructive/10 p-2 text-sm text-destructive"
          >
            {error}
          </div>
        )}

        {experiment !== null && (
          <div className="space-y-4 pt-2">
            {metrics !== null && <MetricsOverview metrics={metrics} />}
            {confusionMatrix !== null && (
              <ConfusionMatrixSection cm={confusionMatrix} />
            )}
            <GeneListsSection experiment={experiment} />
            {crossValidation !== null && (
              <CrossValidationSection cv={crossValidation} />
            )}
            {enrichmentResults.length > 0 && (
              <EnrichmentSection results={enrichmentResults} />
            )}
            {robustness !== null && <RobustnessSection robustness={robustness} />}
          </div>
        )}
      </div>
    </AnalysisPanelContainer>
  );
}

const ENRICHMENT_OPTIONS: { value: EnrichmentAnalysisType; label: string }[] = [
  { value: "go_function", label: "GO function" },
  { value: "go_component", label: "GO component" },
  { value: "go_process", label: "GO process" },
  { value: "pathway", label: "Pathway" },
  { value: "word", label: "Word" },
];

function EnrichmentToggle({
  value,
  onChange,
}: {
  value: EnrichmentAnalysisType[];
  onChange: (v: EnrichmentAnalysisType[]) => void;
}) {
  return (
    <details className="text-xs">
      <summary className="cursor-pointer select-none text-muted-foreground">
        Enrichment ({value.length})
      </summary>
      <div className="mt-2 flex flex-wrap gap-3">
        {ENRICHMENT_OPTIONS.map((opt) => (
          <label key={opt.value} className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={value.includes(opt.value)}
              onChange={(e) => {
                const next = e.target.checked
                  ? [...value, opt.value]
                  : value.filter((v) => v !== opt.value);
                onChange(next);
              }}
            />
            {opt.label}
          </label>
        ))}
      </div>
    </details>
  );
}
