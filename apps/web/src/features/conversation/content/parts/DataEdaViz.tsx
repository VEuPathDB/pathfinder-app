"use client";

import { useState } from "react";
import { Check, ChevronsDownUp, ChevronsUpDown, Copy } from "lucide-react";
import type { EdaViz } from "@pathfinder/shared";

import { Button } from "@/components/ui/button";
import { Figure } from "@/features/conversation/thread/Figure";
import { OpenInSiteLink } from "@/lib/components/OpenInSiteLink";
import { ScatterChart } from "@/lib/components/charts/ScatterChart";
import { VolcanoChart } from "@/lib/components/charts/VolcanoChart";
import type {
  EdaScatterSeries,
  VolcanoThresholds,
} from "@/lib/components/charts/types";
import { comparisonLine } from "@/lib/eda/comparison";
import { selectVolcanoGenes } from "@/lib/eda/volcanoSelection";
import { useEdaStore, useHydrateEdaPart } from "@/state/eda";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { analysisSiteLinkFor, studyNameFor } from "./analysisStateParts";
import { figureNumberFor } from "./figureNumbers";
import { plotCaption } from "./plotCaptions";

const COLLAPSED_HEIGHT = 220;
const EXPANDED_HEIGHT = 480;
const GENE_LIST_LIMIT = 12;
const SIGNIFICANCE_FIELD = "adjustedPValue";
const MUTED = "text-[11px] text-muted-foreground";
const READOUT = `mt-1 ${MUTED}`;
const SUMMARY = `cursor-pointer ${MUTED}`;

export function DataEdaViz({ data }: { data: EdaViz }) {
  useHydrateEdaPart({ kind: "viz", data });
  const thresholds = useEdaStore((s) => s.volcanoThresholds);
  const chat = useChatHelpers();
  const [expanded, setExpanded] = useState(true);
  const height = expanded ? EXPANDED_HEIGHT : COLLAPSED_HEIGHT;
  const study = studyNameFor(chat.messages, data.analysisId);
  const siteLink = analysisSiteLinkFor(chat.messages, data.analysisId);
  const retained = `${data.retainedPoints.toLocaleString()} of ${data.totalPoints.toLocaleString()} genes retained`;

  return (
    <Figure
      testId="data-eda-viz"
      title={data.effectSizeLabel}
      caption={plotCaption(data.caption ?? "", study, retained)}
      exhibit={{ kind: "figure", number: figureNumberFor(chat.messages, data) }}
      footer={<VizReadouts data={data} thresholds={thresholds} />}
      action={
        siteLink !== null ? (
          <OpenInSiteLink href={siteLink.href} siteId={siteLink.siteId} />
        ) : null
      }
    >
      <div>
        {data.comparison != null ? (
          <p data-testid="eda-viz-comparison" className={MUTED}>
            {comparisonLine(data.comparison)}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label={expanded ? "Collapse plot" : "Expand plot"}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? (
              <ChevronsDownUp className="size-3.5" aria-hidden />
            ) : (
              <ChevronsUpDown className="size-3.5" aria-hidden />
            )}
          </Button>
        </div>
        <VizPlot data={data} height={height} thresholds={thresholds} />
      </div>
    </Figure>
  );
}

interface VizBodyProps {
  data: EdaViz;
  height: number;
  thresholds: VolcanoThresholds;
}

function VizPlot({ data, height, thresholds }: VizBodyProps) {
  if (data.points.length === 0) {
    return (
      <p data-testid="data-eda-viz-empty" className={READOUT}>
        This compute returned no points.
      </p>
    );
  }
  switch (data.chart) {
    case "volcano":
      return (
        <VolcanoChart
          points={data.points}
          thresholds={thresholds}
          significanceField={SIGNIFICANCE_FIELD}
          effectSizeLabel={data.effectSizeLabel}
          comparison={data.comparison}
          height={height}
          testId="eda-viz-volcano"
        />
      );
    case "scatter":
      return (
        <ScatterChart
          series={[scatterSeries(data)]}
          xAxis={{ variableId: "effectSize", displayName: data.effectSizeLabel }}
          yAxis={{ variableId: "pValue", displayName: "-log10(p-value)" }}
          height={height}
          testId="eda-viz-scatter"
        />
      );
    case "histogram":
    case "bar":
    case "boxplot":
      return (
        <p data-testid="data-eda-viz-unsupported-chart" className={READOUT}>
          {`${data.chart} plots are not available from this compute, which returns one point per gene.`}
        </p>
      );
  }
}

/** The readouts and disclosures that belong under the caption. A chart the
 * thread cannot draw has none. */
function VizReadouts({
  data,
  thresholds,
}: {
  data: EdaViz;
  thresholds: VolcanoThresholds;
}) {
  if (data.points.length === 0) return null;
  switch (data.chart) {
    case "volcano":
      return <VolcanoReadouts data={data} thresholds={thresholds} />;
    case "scatter":
      return (
        <p data-testid="eda-viz-scatter-count" className={READOUT}>
          {`${scatterSeries(data).x.length.toLocaleString()} of ${data.totalPoints.toLocaleString()} points plotted`}
        </p>
      );
    case "histogram":
    case "bar":
    case "boxplot":
      return null;
  }
}

function VolcanoReadouts({
  data,
  thresholds,
}: {
  data: EdaViz;
  thresholds: VolcanoThresholds;
}) {
  const { selected } = selectVolcanoGenes(data.points, thresholds, SIGNIFICANCE_FIELD);
  const listed = selected.slice(0, GENE_LIST_LIMIT);
  const hidden = selected.length - listed.length;

  return (
    <>
      <p data-testid="eda-viz-volcano-selection" className={READOUT}>
        {`${selected.length.toLocaleString()} ${selected.length === 1 ? "gene" : "genes"} selected at these thresholds - ${data.retainedPoints.toLocaleString()} of ${data.totalPoints.toLocaleString()} retained by the compute`}
      </p>
      {listed.length > 0 ? (
        <details className="mt-1">
          <summary className={`${SUMMARY} [&::marker]:content-none`}>
            <span className="inline-flex items-center gap-1">
              {`Gene ids (${selected.length.toLocaleString()})`}
              <CopyGeneIds ids={selected} />
            </span>
          </summary>
          <p data-testid="eda-viz-volcano-genes" className={READOUT}>
            {hidden > 0
              ? `${listed.join(", ")} and ${hidden.toLocaleString()} more`
              : listed.join(", ")}
          </p>
        </details>
      ) : null}
    </>
  );
}

/** One scatter series in volcano coordinates. A point with no usable p-value
 * has no y and is left out. */
function scatterSeries(data: EdaViz): EdaScatterSeries {
  const x: number[] = [];
  const y: number[] = [];
  const pointIds: string[] = [];
  for (const point of data.points) {
    const pValue = point.pValue;
    if (pValue === null || !Number.isFinite(pValue) || pValue <= 0) continue;
    x.push(point.effectSize);
    y.push(-Math.log10(pValue));
    pointIds.push(point.pointId);
  }
  return { name: "Genes", x, y, pointIds };
}

/** Copies every selected gene id, comma separated. The label flips to a
 * check for a moment so the click answers itself. */
function CopyGeneIds({ ids }: { ids: readonly string[] }) {
  const [copied, setCopied] = useState(false);
  const copy = (event: React.MouseEvent) => {
    // A summary click toggles the disclosure; copying must not.
    event.preventDefault();
    event.stopPropagation();
    void navigator.clipboard.writeText(ids.join(", "));
    setCopied(true);
    window.setTimeout(() => {
      setCopied(false);
    }, 1500);
  };
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      aria-label="Copy gene ids"
      data-testid="eda-viz-copy-gene-ids"
      onClick={copy}
    >
      {copied ? (
        <Check className="size-3" aria-hidden />
      ) : (
        <Copy className="size-3" aria-hidden />
      )}
    </Button>
  );
}
