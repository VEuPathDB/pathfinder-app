"use client";

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import { useUnmount } from "usehooks-ts";
import { BarChart3, Loader2, Play } from "lucide-react";

import type { ControlSet, GeneSet } from "@pathfinder/shared";
import type { CreateBenchmarkRequest } from "@pathfinder/shared/generated/types/CreateBenchmarkRequest";
import {
  createBenchmarkStream,
  experimentBase,
  experimentBasis,
  experimentBlocked,
} from "@/features/workbench/api";
import { Button } from "@/components/ui/button";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { toUserMessage } from "@/lib/api/errors";
import { useSessionStore } from "@/state/useSessionStore";
import { useWorkbenchStore, type PanelId } from "@/state/useWorkbenchStore";

import { controlSetsOptions } from "../../api/controlSets";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import {
  ExperimentComparisonTable,
  type ExperimentRow,
} from "./ExperimentComparisonTable";

const PANEL_ID: PanelId = "benchmark";

export function BenchmarkPanel() {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);
  const { activeSetId, positiveControls, negativeControls } = useWorkbenchStore(
    useShallow((s) => ({
      activeSetId: s.activeSetId,
      positiveControls: s.positiveControls,
      negativeControls: s.negativeControls,
    })),
  );
  const activeSet = geneSets.find((gs) => gs.id === activeSetId);
  if (!activeSet) return null;

  return (
    <AnalysisPanelContainer
      panelId={PANEL_ID}
      title="Benchmark (multi-control-set)"
      subtitle="Score this set against several saved control sets"
      icon={<BarChart3 className="h-5 w-5" />}
    >
      <BenchmarkRunner
        geneSet={activeSet}
        positiveControls={positiveControls}
        negativeControls={negativeControls}
      />
    </AnalysisPanelContainer>
  );
}

interface BenchmarkRunnerProps {
  geneSet: GeneSet;
  positiveControls: string[];
  negativeControls: string[];
}

function BenchmarkRunner({
  geneSet,
  positiveControls,
  negativeControls,
}: BenchmarkRunnerProps) {
  const blocked = experimentBlocked(experimentBasis(geneSet));
  const controlSets = useQuery(controlSetsOptions(geneSet.siteId));

  const [chosenIds, setChosenIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<ExperimentRow[] | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useUnmount(() => abortRef.current?.abort());

  if (blocked !== null) {
    return <p className="text-xs text-muted-foreground">{blocked}</p>;
  }
  if (controlSets.isPending) {
    return <p className="text-xs text-muted-foreground">Loading control sets...</p>;
  }

  const available = controlSets.data ?? [];
  if (available.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        A benchmark compares saved control sets. Save one from the Evaluate panel first.
      </p>
    );
  }

  const chosen = chosenIds
    .map((id) => available.find((cs) => cs.id === id))
    .filter((cs): cs is ControlSet => cs != null);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setRows(null);
    setProgressText("");

    const controller = new AbortController();
    abortRef.current = controller;
    const request: CreateBenchmarkRequest = {
      base: experimentBase({
        geneSet,
        positiveControls,
        negativeControls,
        run: "benchmark",
      }),
      controlSets: chosen.map((cs, index) => ({
        label: cs.name,
        positiveControls: cs.positiveIds,
        negativeControls: cs.negativeIds,
        controlSetId: cs.id,
        isPrimary: index === 0,
      })),
    };

    try {
      for await (const event of createBenchmarkStream(request, {
        signal: controller.signal,
      })) {
        if (event.type === "experiment_progress") {
          const raw = event.data;
          const phase = typeof raw["phase"] === "string" ? raw["phase"] : undefined;
          if (phase !== undefined) setProgressText(phase);
        } else if (event.type === "benchmark_complete") {
          setRows(
            event.experiments.map((experiment) => ({
              label:
                experiment.controlSetLabel ?? experiment.config.name ?? experiment.id,
              experiment,
            })),
          );
        } else {
          setError(event.error);
        }
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(toUserMessage(err, "The benchmark did not run."));
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">
          Control sets to score against
        </p>
        <div className="flex flex-wrap gap-1.5">
          {available.map((cs) => {
            const selected = chosenIds.includes(cs.id);
            return (
              <button
                key={cs.id}
                type="button"
                data-testid="benchmark-control-set"
                data-control-set-id={cs.id}
                aria-pressed={selected}
                onClick={() =>
                  setChosenIds(
                    selected
                      ? chosenIds.filter((id) => id !== cs.id)
                      : [...chosenIds, cs.id],
                  )
                }
                className={`rounded-full border px-2.5 py-0.5 text-[10px] font-medium transition-colors ${
                  selected
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input text-muted-foreground hover:border-foreground/30"
                }`}
              >
                {cs.name} ({cs.positiveIds.length}+ / {cs.negativeIds.length}-)
              </button>
            );
          })}
        </div>
      </div>

      {chosen.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Choose at least one control set: a benchmark is one run per set.
        </p>
      )}

      <Button
        onClick={() => void handleRun()}
        disabled={loading || chosen.length === 0}
        className="gap-2"
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Play className="h-4 w-4" />
        )}
        {loading ? "Running..." : `Run ${chosen.length} control sets`}
      </Button>

      {loading && progressText !== "" && (
        <div className="text-xs text-muted-foreground">Phase: {progressText}</div>
      )}

      {error !== null && error !== "" && (
        <div
          data-testid="benchmark-error"
          className="rounded border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive"
        >
          {error}
        </div>
      )}

      {rows !== null && (
        <ExperimentComparisonTable
          runHeader="Control set"
          rows={rows}
          testId="benchmark-results"
        />
      )}
    </div>
  );
}
