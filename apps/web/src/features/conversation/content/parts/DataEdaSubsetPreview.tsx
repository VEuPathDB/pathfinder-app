"use client";

import type { EdaDistributionSeries, EdaSubsetPreview } from "@pathfinder/shared";

import { HistogramChart } from "@/lib/components/charts/HistogramChart";
import { Figure } from "@/features/conversation/thread/Figure";
import { useHydrateEdaPart } from "@/state/eda";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { studyNameFor } from "./analysisStateParts";
import { entityCountCaption } from "./entityCounts";
import { figureNumberFor } from "./figureNumbers";
import { plotCaption } from "./plotCaptions";

// The chart's grid reserves 64px for its axes, so the plot area is the
// height minus that; 220 matches the collapsed volcano.
const HISTOGRAM_HEIGHT = 220;
const MUTED = "text-[11px] text-muted-foreground";
const SUMMARY = `cursor-pointer ${MUTED}`;
const MULTIVALUED_NOTE =
  "one record can carry several values, so these counts do not add up to the subset size";

function variableName(series: EdaDistributionSeries): string {
  return series.variableDisplayName.length > 0
    ? series.variableDisplayName
    : series.variableId;
}

export function DataEdaSubsetPreview({ data }: { data: EdaSubsetPreview }) {
  useHydrateEdaPart({ kind: "subset-preview", data });
  const chat = useChatHelpers();
  const note = data.distributionNote ?? "";
  const series = data.distribution;
  const counts = entityCountCaption(data.entityCounts);
  const study = studyNameFor(chat.messages, data.analysisId);
  const base =
    series !== null
      ? `${counts}, ${series.numVarValues.toLocaleString()} values`
      : counts;

  return (
    <Figure
      testId="data-eda-subset-preview"
      title={series !== null ? variableName(series) : null}
      caption={plotCaption(data.caption ?? "", study, base)}
      exhibit={{ kind: "figure", number: figureNumberFor(chat.messages, data) }}
      footer={
        <div className="text-xs">
          {series !== null ? <DistributionReadouts series={series} /> : null}
          {note.length > 0 ? (
            <p data-testid="data-eda-subset-note" className={`mt-1 ${MUTED}`}>
              {note}
            </p>
          ) : null}
        </div>
      }
    >
      {series !== null ? <Distribution series={series} /> : null}
    </Figure>
  );
}

function Distribution({ series }: { series: EdaDistributionSeries }) {
  const name = variableName(series);
  return (
    <div className="mt-2">
      <HistogramChart
        series={[{ name, labels: series.labels, values: series.values }]}
        barMode="stack"
        valueLabel="Records"
        height={HISTOGRAM_HEIGHT}
        testId="data-eda-subset-histogram"
        ariaLabel={`${name} distribution over the subset`}
      />
    </div>
  );
}

/** The bin counts behind a disclosure, and the science that changes an
 * interpretation: how many records carry a value, and whether the bars can
 * add up at all. */
function DistributionReadouts({ series }: { series: EdaDistributionSeries }) {
  const missing = series.numMissingCases > 0;
  const coverage = (
    <p data-testid="data-eda-subset-coverage" className={`mt-1 ${MUTED}`}>
      {`${String(series.numVarValues)} of ${String(series.subsetSize)} records have a value`}
      {missing ? `, ${String(series.numMissingCases)} missing` : ""}
    </p>
  );

  return (
    <>
      <details className="mt-1">
        <summary className={SUMMARY}>Bin counts</summary>
        <ul className={`mt-1 flex flex-wrap gap-x-3 ${MUTED}`}>
          {series.labels.map((label, index) => (
            <li key={label} data-testid={`data-eda-subset-bin-${String(index)}`}>
              {`${label} ${(series.values[index] ?? 0).toLocaleString()}`}
            </li>
          ))}
        </ul>
        {missing ? null : coverage}
      </details>
      {missing ? coverage : null}
      {series.isMultiValued ? (
        <p data-testid="data-eda-subset-multivalued" className={`mt-1 ${MUTED}`}>
          {MULTIVALUED_NOTE}
        </p>
      ) : null}
    </>
  );
}
