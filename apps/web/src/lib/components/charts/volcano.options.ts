import type { ChartTokens } from "./chartTheme";
import { selectVolcanoGenes } from "@/lib/eda/volcanoSelection";
import type {
  VolcanoPointInput,
  VolcanoSignificanceField,
  VolcanoThresholds,
} from "./types";

export type VolcanoPoint = [number, number, string];

interface VolcanoSeries {
  name: string;
  data: VolcanoPoint[];
  itemStyle: { color: string; opacity: number };
}

interface VolcanoThresholdLine {
  axis: "x" | "y";
  value: number;
}

export interface VolcanoOptionModel {
  series: VolcanoSeries[];
  thresholdLines: VolcanoThresholdLine[];
  xAxis: { name: string };
  yAxis: { name: string };
  droppedRowCount: number;
}

export interface BuildVolcanoOptionArgs {
  points: readonly VolcanoPointInput[];
  thresholds: VolcanoThresholds;
  significanceField: VolcanoSignificanceField;
  effectSizeLabel: string;
  tokens: ChartTokens;
}

export function volcanoPointY(pValue: number | null | undefined): number | null {
  if (pValue === null || pValue === undefined) return null;
  if (!Number.isFinite(pValue) || pValue <= 0) return null;
  return -Math.log10(pValue);
}

export function buildVolcanoOption(args: BuildVolcanoOptionArgs): VolcanoOptionModel {
  const selection = selectVolcanoGenes(
    args.points,
    args.thresholds,
    args.significanceField,
  );
  const upIds = new Set(selection.up);
  const downIds = new Set(selection.down);

  const neutral: VolcanoPoint[] = [];
  const up: VolcanoPoint[] = [];
  const down: VolcanoPoint[] = [];
  let droppedRowCount = 0;

  for (const point of args.points) {
    const y = volcanoPointY(point.pValue);
    if (!Number.isFinite(point.effectSize) || y === null) {
      droppedRowCount += 1;
      continue;
    }
    const plotted: VolcanoPoint = [point.effectSize, y, point.pointId];
    if (upIds.has(point.pointId)) up.push(plotted);
    else if (downIds.has(point.pointId)) down.push(plotted);
    else neutral.push(plotted);
  }

  return {
    series: [
      {
        name: "Not notable",
        data: neutral,
        itemStyle: { color: args.tokens.mutedForeground, opacity: 0.35 },
      },
      {
        name: "Higher in group B",
        data: up,
        itemStyle: { color: args.tokens.positive, opacity: 0.85 },
      },
      {
        name: "Higher in group A",
        data: down,
        itemStyle: { color: args.tokens.negative, opacity: 0.85 },
      },
    ],
    thresholdLines: [
      { axis: "x", value: -args.thresholds.effectSizeThreshold },
      { axis: "x", value: args.thresholds.effectSizeThreshold },
      { axis: "y", value: -Math.log10(args.thresholds.significanceThreshold) },
    ],
    xAxis: { name: args.effectSizeLabel },
    yAxis: { name: "-log10(p-value)" },
    droppedRowCount,
  };
}
