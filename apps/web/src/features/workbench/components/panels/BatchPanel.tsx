"use client";

import { useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { useUnmount } from "usehooks-ts";
import { Layers, Loader2, Play } from "lucide-react";

import type { Experiment } from "@pathfinder/shared";
import {
  createBatchExperimentStream,
  type BatchOrganismTarget,
} from "@/features/workbench/api";
import type { ExperimentRunConfig } from "@/features/workbench/api/streaming";
import { Button } from "@/components/ui/button";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { useSessionStore } from "@/state/useSessionStore";
import { useWorkbenchStore, type PanelId } from "@/state/useWorkbenchStore";

import { AnalysisPanelContainer } from "../AnalysisPanelContainer";

const PANEL_ID: PanelId = "batch";

export function BatchPanel() {
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

  const [organismsInput, setOrganismsInput] = useState("");
  const [organismParamName, setOrganismParamName] = useState("organism");
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [experiments, setExperiments] = useState<Experiment[] | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useUnmount(() => abortRef.current?.abort());

  const parsedTargets: BatchOrganismTarget[] = organismsInput
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((organism) => ({ organism }));

  const canRun =
    activeSet != null &&
    positiveControls.length > 0 &&
    parsedTargets.length > 0 &&
    organismParamName.length > 0;

  const handleRun = async () => {
    if (!activeSet) return;
    setLoading(true);
    setError(null);
    setExperiments(null);
    setProgressText("");

    const controller = new AbortController();
    abortRef.current = controller;

    const base = {
      siteId: activeSet.siteId,
      recordType: activeSet.recordType ?? "gene",
      searchName: activeSet.searchName ?? "",
      parameters: activeSet.parameters ?? {},
      positiveControls,
      negativeControls,
      name: `${activeSet.name} (batch)`,
    } satisfies ExperimentRunConfig;

    try {
      for await (const event of createBatchExperimentStream(
        base,
        organismParamName,
        parsedTargets,
        { signal: controller.signal },
      )) {
        if (event.type === "experiment_progress") {
          const raw = event.data;
          const phase = typeof raw["phase"] === "string" ? raw["phase"] : undefined;
          if (phase !== undefined) setProgressText(phase);
        } else if (event.type === "batch_complete") {
          setExperiments(event.experiments);
        } else {
          setError(event.error);
        }
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(err instanceof Error ? err.message : "Batch experiment failed");
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
      title="Batch (multi-organism)"
      subtitle="Run the active experiment across multiple organisms"
      icon={<Layers className="h-5 w-5" />}
    >
      <div className="space-y-3 text-sm">
        <label className="block space-y-1">
          <span className="text-xs font-medium uppercase text-muted-foreground">
            Organism parameter name
          </span>
          <input
            type="text"
            value={organismParamName}
            onChange={(e) => setOrganismParamName(e.target.value)}
            className="w-full rounded border border-input bg-background px-2 py-1"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-xs font-medium uppercase text-muted-foreground">
            Organisms (one per line)
          </span>
          <textarea
            value={organismsInput}
            onChange={(e) => setOrganismsInput(e.target.value)}
            className="h-32 w-full rounded border border-input bg-background px-2 py-1 font-mono text-xs"
            placeholder="Plasmodium falciparum&#10;Plasmodium berghei&#10;Plasmodium vivax"
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
          {loading ? "Running..." : `Run ${parsedTargets.length} experiments`}
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
