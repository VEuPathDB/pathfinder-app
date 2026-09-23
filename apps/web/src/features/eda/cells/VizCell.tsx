"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import type { EdaViz } from "@pathfinder/shared";

import { Spinner } from "@/components/ui/spinner";
import { edaViz } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { comparisonLine } from "@/lib/eda/comparison";
import { isEdaJobComplete, useEdaStore, type EdaJobSnapshot } from "@/state/eda";

import { CellShell } from "./CellShell";
import { ScatterPanel } from "./ScatterPanel";
import { VolcanoPanel } from "./VolcanoPanel";

const VIZ_FAILED = "Could not read the compute's plot";
const NOTHING_TO_PLOT = "Run a compute to see its plots.";

export interface VizCellProps {
  siteId: string;
  conversationId: string;
}

/** The chart the analysis produced most recently. */
function latestViz(viz: Record<string, EdaViz>): EdaViz | null {
  const charts = Object.keys(viz);
  const last = charts[charts.length - 1];
  return last === undefined ? null : (viz[last] ?? null);
}

/** The job whose plot the cell shows: the last one to reach complete. */
function latestCompleteJobId(jobs: Record<string, EdaJobSnapshot>): string | null {
  const complete = Object.values(jobs).filter(isEdaJobComplete);
  return complete[complete.length - 1]?.jobId ?? null;
}

export function VizCell({ siteId, conversationId }: VizCellProps) {
  const viz = useEdaStore((s) => s.viz);
  const jobs = useEdaStore((s) => s.jobs);
  const binding = useEdaStore((s) => s.binding);
  const current = latestViz(viz);
  const datasetId = binding?.datasetId ?? "";
  const analysisId = binding?.analysisId ?? "";
  const jobId = latestCompleteJobId(jobs);

  const volcano = useQuery({
    queryKey: ["eda", "viz", conversationId, datasetId, jobId] as const,
    queryFn: async (): Promise<EdaViz> => {
      const response = await edaViz({
        siteId,
        conversationId,
        datasetId,
        chart: "volcano",
      });
      const part: EdaViz = { datasetId, analysisId, ...response };
      useEdaStore.getState().applyViz(part);
      return part;
    },
    enabled: jobId !== null && datasetId !== "" && analysisId !== "",
    retry: false,
    staleTime: Infinity,
  });

  const [reported, setReported] = useState<unknown>(null);
  if (volcano.error != null && reported !== volcano.error) {
    setReported(volcano.error);
    const message = toUserMessage(volcano.error, VIZ_FAILED);
    queueMicrotask(() => toast.error(message));
  }

  return (
    <CellShell
      title="Visualization"
      subtitle={current?.comparison != null ? comparisonLine(current.comparison) : null}
      testId="eda-viz-cell"
    >
      <VizBody
        payload={current}
        error={volcano.error}
        isFetching={volcano.isFetching}
      />
    </CellShell>
  );
}

function VizBody({
  payload,
  error,
  isFetching,
}: {
  payload: EdaViz | null;
  error: unknown;
  isFetching: boolean;
}) {
  if (error != null) {
    return (
      <p data-testid="eda-viz-error" className="text-xs text-destructive">
        {toUserMessage(error, VIZ_FAILED)}
      </p>
    );
  }
  if (payload === null) {
    if (isFetching) {
      return (
        <div data-testid="eda-viz-loading" className="flex justify-center py-4">
          <Spinner className="size-4" />
        </div>
      );
    }
    return (
      <p data-testid="eda-viz-unavailable" className="text-xs text-muted-foreground">
        {NOTHING_TO_PLOT}
      </p>
    );
  }
  switch (payload.chart) {
    case "volcano":
      return <VolcanoPanel payload={payload} />;
    case "scatter":
      return <ScatterPanel payload={payload} />;
    case "histogram":
    case "bar":
    case "boxplot":
      return <UnsupportedChartNotice chart={payload.chart} />;
  }
}

function UnsupportedChartNotice({ chart }: { chart: string }) {
  return (
    <p
      data-testid="eda-viz-unsupported-chart"
      className="text-xs text-muted-foreground"
    >
      {`${chart} plots are not available from this compute, which returns one point per gene.`}
    </p>
  );
}
