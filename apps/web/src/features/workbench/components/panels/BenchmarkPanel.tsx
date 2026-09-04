"use client";

import { useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useUnmount } from "usehooks-ts";
import { BarChart3, Loader2, Play } from "lucide-react";

import type { Experiment } from "@pathfinder/shared";
import {
  createBenchmarkStream,
  type BenchmarkControlSetInput,
} from "@/features/workbench/api";
import type { ExperimentRunConfig } from "@/features/workbench/api/streaming";
import { Button } from "@/components/ui/button";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { useSessionStore } from "@/state/useSessionStore";
import { useWorkbenchStore, type PanelId } from "@/state/useWorkbenchStore";

import { AnalysisPanelContainer } from "../AnalysisPanelContainer";

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

  const [controlSetsJson, setControlSetsJson] = useState<string>(
    JSON.stringify(
      [
        {
          label: "Primary",
          positiveControls: [],
          negativeControls: [],
          isPrimary: true,
        },
      ],
      null,
      2,
    ),
  );
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [experiments, setExperiments] = useState<Experiment[] | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useUnmount(() => abortRef.current?.abort());

  const canRun = activeSet != null && controlSetsJson.trim().length > 0;

  const handleRun = async () => {
    if (!activeSet) return;
    setLoading(true);
    setError(null);
    setExperiments(null);
    setProgressText("");

    let parsedControlSets: BenchmarkControlSetInput[];
    try {
      parsedControlSets = JSON.parse(controlSetsJson) as BenchmarkControlSetInput[];
    } catch {
      setError("Control sets JSON is malformed.");
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const base = {
      siteId: activeSet.siteId,
      recordType: activeSet.recordType ?? "gene",
      searchName: activeSet.searchName ?? "",
      parameters: activeSet.parameters ?? {},
      positiveControls,
      negativeControls,
      name: `${activeSet.name} (benchmark)`,
    } satisfies ExperimentRunConfig;

    try {
      for await (const event of createBenchmarkStream(base, parsedControlSets, {
        signal: controller.signal,
      })) {
        if (event.type === "experiment_progress") {
          const raw = event.data;
          const phase = typeof raw["phase"] === "string" ? raw["phase"] : undefined;
          if (phase !== undefined) setProgressText(phase);
        } else if (event.type === "benchmark_complete") {
          setExperiments(event.experiments);
        } else {
          setError(event.error);
        }
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(err instanceof Error ? err.message : "Benchmark failed");
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  if (!activeSet) return null;

  return (
    <AnalysisPanelContainer
      panelId={PANEL_ID}
      title="Benchmark (multi-control-set)"
      subtitle="Benchmark the active strategy against multiple control sets"
      icon={<BarChart3 className="h-5 w-5" />}
    >
      <div className="space-y-3 text-sm">
        <label className="block space-y-1">
          <span className="text-xs font-medium uppercase text-muted-foreground">
            Control sets (JSON)
          </span>
          <textarea
            value={controlSetsJson}
            onChange={(e) => setControlSetsJson(e.target.value)}
            className="h-48 w-full rounded border border-input bg-background px-2 py-1 font-mono text-xs"
          />
        </label>

        <Button
          onClick={() => void handleRun()}
          disabled={loading || !canRun}
          className="gap-2"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          {loading ? "Running..." : "Run benchmark"}
        </Button>

        {loading && progressText !== "" && (
          <div className="text-xs text-muted-foreground">Phase: {progressText}</div>
        )}

        {error !== null && error !== "" && (
          <div className="rounded border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </div>
        )}

        {experiments && (
          <details className="rounded border border-border p-2 text-xs">
            <summary className="cursor-pointer font-medium">
              {experiments.length} experiments complete
            </summary>
            <pre className="mt-2 max-h-96 overflow-auto">
              <code>{JSON.stringify(experiments, null, 2)}</code>
            </pre>
          </details>
        )}
      </div>
    </AnalysisPanelContainer>
  );
}
