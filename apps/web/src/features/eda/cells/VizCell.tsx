"use client";

import { useQuery } from "@tanstack/react-query";
import type { EdaViz } from "@pathfinder/shared";

import { Spinner } from "@/components/ui/spinner";
import { edaViz } from "@/features/eda/api";
import { toUserMessage } from "@/lib/api/errors";
import { comparisonLine } from "@/lib/eda/comparison";
import { useEdaStore } from "@/state/eda";

import { CellShell } from "./CellShell";
import { ScatterPanel } from "./ScatterPanel";
import { VolcanoPanel } from "./VolcanoPanel";

const VIZ_FAILED = "Could not read the comparison's plot";

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

/** The figure of the comparison the analysis holds, read from the site on every
 * mount so an edit made on the site shows. */
export function VizCell({ siteId, conversationId }: VizCellProps) {
  const viz = useEdaStore((s) => s.viz);
  const binding = useEdaStore((s) => s.binding);
  const revision = useEdaStore((s) => s.analysis?.revision ?? null);
  const current = latestViz(viz);
  const datasetId = binding?.datasetId ?? "";
  const analysisId = binding?.analysisId ?? "";

  const volcano = useQuery({
    queryKey: ["eda", "viz", conversationId, analysisId, revision] as const,
    queryFn: async (): Promise<EdaViz> => {
      const response = await edaViz({ siteId, conversationId, chart: "volcano" });
      const part: EdaViz = { datasetId, analysisId, ...response };
      useEdaStore.getState().applyViz(part);
      return part;
    },
    enabled: datasetId !== "" && analysisId !== "",
    retry: false,
    staleTime: 0,
    meta: { shownInline: true },
  });

  return (
    <CellShell
      title="Figure"
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
    return isFetching ? (
      <div data-testid="eda-viz-loading" className="flex justify-center py-4">
        <Spinner className="size-4" />
      </div>
    ) : null;
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
      {`${chart} plots are not available from this comparison, which returns one point per gene.`}
    </p>
  );
}
