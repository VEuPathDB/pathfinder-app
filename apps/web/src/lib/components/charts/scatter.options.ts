import type { ChartTokens } from "./chartTheme";
import type { EdaAxisLabel, EdaScatterSeries } from "./types";
import { UNRESOLVED_SERIES_COLOR } from "./unresolved";

type ScatterPoint = [number, number, string];

export interface ScatterOptionModel {
  series: { name: string; points: ScatterPoint[]; color: string }[];
  xAxisName: string;
  yAxisName: string;
  droppedPointCount: number;
}

export interface BuildScatterOptionArgs {
  series: readonly EdaScatterSeries[];
  xAxis: EdaAxisLabel;
  yAxis: EdaAxisLabel;
  tokens: ChartTokens;
}

export function buildScatterOption(args: BuildScatterOptionArgs): ScatterOptionModel {
  const fallbackColor = args.tokens.series[0] ?? UNRESOLVED_SERIES_COLOR;
  let droppedPointCount = 0;

  const series = args.series.map((entry, index) => {
    const length = Math.min(entry.x.length, entry.y.length);
    const points: ScatterPoint[] = [];
    for (let i = 0; i < length; i += 1) {
      const x = entry.x[i];
      const y = entry.y[i];
      if (
        x === undefined ||
        y === undefined ||
        !Number.isFinite(x) ||
        !Number.isFinite(y)
      ) {
        droppedPointCount += 1;
        continue;
      }
      points.push([x, y, entry.pointIds?.[i] ?? entry.name]);
    }
    return {
      name: entry.name,
      points,
      color: args.tokens.series[index % args.tokens.series.length] ?? fallbackColor,
    };
  });

  return {
    series,
    xAxisName: args.xAxis.displayName,
    yAxisName: args.yAxis.displayName,
    droppedPointCount,
  };
}
