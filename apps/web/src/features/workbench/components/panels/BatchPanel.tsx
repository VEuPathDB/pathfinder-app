"use client";

import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import { useUnmount } from "usehooks-ts";
import { Layers, Loader2, Play, X } from "lucide-react";

import type { Experiment, GeneSet } from "@pathfinder/shared";
import { getOrganismsQueryOptions } from "@pathfinder/shared/generated/hooks/useGetOrganisms";
import type { CreateBatchExperimentRequest } from "@pathfinder/shared/generated/types/CreateBatchExperimentRequest";
import {
  createBatchExperimentStream,
  experimentBase,
  experimentBasis,
  organismBlocked,
  organismParamOf,
} from "@/features/workbench/api";
import { Button } from "@/components/ui/button";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { toUserMessage } from "@/lib/api/errors";
import { paramSpecsOptions } from "@/lib/api/sites";
import { useSessionStore } from "@/state/useSessionStore";
import { useWorkbenchStore, type PanelId } from "@/state/useWorkbenchStore";

import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { OrganismFilter } from "../OrganismFilter";
import {
  ExperimentComparisonTable,
  type ExperimentRow,
} from "./ExperimentComparisonTable";

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
  if (!activeSet) return null;

  return (
    <AnalysisPanelContainer
      panelId={PANEL_ID}
      title="Batch (multi-organism)"
      subtitle="Run this set's search once per organism"
      icon={<Layers className="h-5 w-5" />}
    >
      <BatchRunner
        geneSet={activeSet}
        positiveControls={positiveControls}
        negativeControls={negativeControls}
      />
    </AnalysisPanelContainer>
  );
}

interface BatchRunnerProps {
  geneSet: GeneSet;
  positiveControls: string[];
  negativeControls: string[];
}

function BatchRunner({
  geneSet,
  positiveControls,
  negativeControls,
}: BatchRunnerProps) {
  const basis = experimentBasis(geneSet);
  const blocked = organismBlocked(geneSet);
  const recordType = geneSet.recordType ?? "gene";
  const searchName = basis.kind === "search" ? basis.searchName : "";

  const specs = useQuery(paramSpecsOptions(geneSet.siteId, recordType, searchName));
  const organisms = useQuery({
    ...getOrganismsQueryOptions(geneSet.siteId),
    enabled: blocked === null,
  });

  const [chosen, setChosen] = useState<string[]>([]);
  const [organismFilter, setOrganismFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [progressText, setProgressText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<ExperimentRow[] | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useUnmount(() => abortRef.current?.abort());

  if (blocked !== null) {
    return <PanelNotice>{blocked}</PanelNotice>;
  }
  if (specs.isPending || organisms.isPending) {
    return <PanelNotice>Reading the parameters of {searchName}...</PanelNotice>;
  }

  const organismParam = organismParamOf(
    specs.data ?? [],
    organisms.data?.organisms ?? [],
  );
  if (organismParam === null) {
    return (
      <PanelNotice>
        {searchName} declares no organism parameter, so it cannot be run one organism at
        a time.
      </PanelNotice>
    );
  }

  const offered = organismParam.organisms.filter(
    (org) =>
      !chosen.includes(org) && org.toLowerCase().includes(organismFilter.toLowerCase()),
  );
  const missingControls = positiveControls.length === 0;
  const canRun = chosen.length > 0 && !missingControls;

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    setRows(null);
    setProgressText("");

    const controller = new AbortController();
    abortRef.current = controller;
    const request: CreateBatchExperimentRequest = {
      base: experimentBase({
        geneSet,
        positiveControls,
        negativeControls,
        run: "batch",
      }),
      organismParamName: organismParam.name,
      targetOrganisms: chosen.map((organism) => ({ organism })),
    };

    try {
      for await (const event of createBatchExperimentStream(request, {
        signal: controller.signal,
      })) {
        if (event.type === "experiment_progress") {
          const raw = event.data;
          const phase = typeof raw["phase"] === "string" ? raw["phase"] : undefined;
          if (phase !== undefined) setProgressText(phase);
        } else if (event.type === "batch_complete") {
          setRows(
            event.experiments.map((experiment) => ({
              label: organismOf(experiment, organismParam.name),
              experiment,
            })),
          );
        } else {
          setError(event.error);
        }
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(toUserMessage(err, "The batch did not run."));
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  };

  return (
    <div className="space-y-3 text-sm">
      <p className="text-xs text-muted-foreground">
        Each run repeats {searchName} with{" "}
        <span className="font-mono">{organismParam.name}</span> set to one organism.
      </p>

      <OrganismFilter
        organisms={organismParam.organisms}
        selectedOrganism={null}
        onSelect={(organism) => {
          if (organism !== null) setChosen([...chosen, organism]);
        }}
        organismFilter={organismFilter}
        onFilterChange={setOrganismFilter}
        filteredOrganisms={offered}
      />

      {chosen.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {chosen.map((organism) => (
            <span
              key={organism}
              data-testid="batch-organism"
              className="inline-flex items-center gap-1 rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] leading-tight"
            >
              <span className="italic">{organism}</span>
              <button
                type="button"
                aria-label={`Remove ${organism}`}
                onClick={() => setChosen(chosen.filter((o) => o !== organism))}
                className="rounded-full p-0.5 hover:bg-muted-foreground/20"
              >
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {missingControls && (
        <p className="text-xs text-muted-foreground">
          Pick positive controls in the Evaluate panel: every organism is scored against
          them.
        </p>
      )}

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
        {loading ? "Running..." : `Run ${chosen.length} experiments`}
      </Button>

      {loading && progressText !== "" && (
        <div className="text-xs text-muted-foreground">Phase: {progressText}</div>
      )}

      {error !== null && error !== "" && (
        <div
          data-testid="batch-error"
          className="rounded border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive"
        >
          {error}
        </div>
      )}

      {rows !== null && (
        <ExperimentComparisonTable
          runHeader="Organism"
          rows={rows}
          testId="batch-results"
        />
      )}
    </div>
  );
}

function PanelNotice({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

/** The organism a finished run was scoped to, read from its own config. */
function organismOf(experiment: Experiment, organismParamName: string): string {
  const value = experiment.config.parameters[organismParamName];
  if (value?.type === "single-pick-vocabulary") return value.value;
  return experiment.config.name ?? experiment.id;
}
