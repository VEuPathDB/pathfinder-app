import type { EChartsOption, TooltipComponentFormatterCallbackParams } from "echarts";
import type { EnrichmentTerm } from "@pathfinder/shared";

import type { ChartTokens } from "@/lib/components/charts/chartTheme";
import {
  compareNullableAsc,
  DOT_MAX_R,
  DOT_MIN_R,
  formatProbability,
  formatRatio,
  MAX_CHART_TERMS,
  truncateLabel,
} from "./enrichment-utils";

type Cell = string | number | Date | null | undefined;

/** A dot carries its fold enrichment, term label, gene count and p-value. */
export type DotPlotPoint = [number, string, number, number | null];

const SERIES_NAME = "Enriched terms";
const ROW_HEIGHT = 28;
const ROW_PADDING = 40;
const MIN_HEIGHT = 140;
const TERM_AXIS_WIDTH = 208;

function dotPlotPoint(
  foldEnrichment: number,
  label: string,
  geneCount: number,
  pValue: number | null,
): DotPlotPoint {
  return [foldEnrichment, label, geneCount, pValue];
}

export function readDotPlotPoint(cells: readonly Cell[]): DotPlotPoint | null {
  const [foldEnrichment, label, geneCount, pValue] = cells;
  if (typeof foldEnrichment !== "number" || typeof label !== "string") return null;
  if (typeof geneCount !== "number") return null;
  if (pValue !== null && typeof pValue !== "number") return null;
  return dotPlotPoint(foldEnrichment, label, geneCount, pValue);
}

export function formatDotPlotTooltip(point: DotPlotPoint): string {
  const [foldEnrichment, label, geneCount, pValue] = point;
  return [
    label,
    `Fold: ${formatRatio(foldEnrichment, 2)}`,
    `Genes: ${String(geneCount)}`,
    `p: ${formatProbability(pValue)}`,
  ].join("<br/>");
}

export function dotPlotTooltip(
  params: TooltipComponentFormatterCallbackParams,
): string {
  const entry = Array.isArray(params) ? params[0] : params;
  const value = entry?.value;
  if (!Array.isArray(value)) return "";
  const point = readDotPlotPoint(value);
  return point === null ? "" : formatDotPlotTooltip(point);
}

export interface BuildEnrichmentDotPlotArgs {
  terms: readonly EnrichmentTerm[];
  tokens: ChartTokens;
  colorForPValue: (pValue: number | null) => string;
}

export interface EnrichmentDotPlotModel {
  option: EChartsOption;
  maxGeneCount: number;
  termCount: number;
  height: number;
}

export function buildEnrichmentDotPlot(
  args: BuildEnrichmentDotPlotArgs,
): EnrichmentDotPlotModel {
  const top = [...args.terms]
    .sort((a, b) => compareNullableAsc(a.pValue, b.pValue))
    .slice(0, MAX_CHART_TERMS)
    .reverse();
  const maxGeneCount = Math.max(...top.map((term) => term.geneCount), 1);
  const labels = top.map((term) =>
    truncateLabel(term.termName || term.termId || "\u2014"),
  );

  const data = top.flatMap((term, index) => {
    if (term.foldEnrichment === null) return [];
    const share = term.geneCount / maxGeneCount;
    return [
      {
        value: dotPlotPoint(
          term.foldEnrichment,
          labels[index] ?? "",
          term.geneCount,
          term.pValue,
        ),
        symbolSize: 2 * (DOT_MIN_R + share * (DOT_MAX_R - DOT_MIN_R)),
        itemStyle: { color: args.colorForPValue(term.pValue), opacity: 0.85 },
      },
    ];
  });

  return {
    maxGeneCount,
    termCount: top.length,
    height: Math.max(top.length * ROW_HEIGHT + ROW_PADDING, MIN_HEIGHT),
    option: {
      animation: false,
      grid: { left: TERM_AXIS_WIDTH, right: 32, top: 8, bottom: 36 },
      xAxis: {
        type: "value",
        name: "Fold Enrichment",
        nameLocation: "middle",
        nameGap: 24,
        axisLabel: { fontSize: 10 },
        splitLine: { lineStyle: { type: "dashed", color: args.tokens.border } },
      },
      yAxis: {
        type: "category",
        data: labels,
        axisLabel: { fontSize: 10 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      tooltip: { trigger: "item", formatter: dotPlotTooltip },
      series: [{ type: "scatter", name: SERIES_NAME, data }],
    },
  };
}
