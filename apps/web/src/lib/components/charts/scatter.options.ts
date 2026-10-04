import type { ChartTokens } from "./chartTheme";
import type { EdaAxisLabel, EdaScatterSeries } from "./types";
import { UNRESOLVED_SERIES_COLOR } from "./unresolved";

type ScatterPoint = [number, number, string];

interface PlottedSeries {
  name: string;
  points: ScatterPoint[];
  color: string;
}

export interface ScatterOptionModel {
  series: PlottedSeries[];
  /** A line drawn over the points, such as a fit. Its vertices are not data
   * points, so a vertex it leaves out is not counted as dropped. */
  line: PlottedSeries | null;
  xAxisName: string;
  yAxisName: string;
  droppedPointCount: number;
}

export interface BuildScatterOptionArgs {
  series: readonly EdaScatterSeries[];
  line?: EdaScatterSeries | undefined;
  xAxis: EdaAxisLabel;
  yAxis: EdaAxisLabel;
  tokens: ChartTokens;
}

/** The finite coordinate pairs of one series, each labelled by its point id or
 * the series name, and how many pairs it left out. */
function plottable(entry: EdaScatterSeries): {
  points: ScatterPoint[];
  dropped: number;
} {
  const length = Math.min(entry.x.length, entry.y.length);
  const points: ScatterPoint[] = [];
  let dropped = 0;
  for (let i = 0; i < length; i += 1) {
    const x = entry.x[i];
    const y = entry.y[i];
    if (
      x === undefined ||
      y === undefined ||
      !Number.isFinite(x) ||
      !Number.isFinite(y)
    ) {
      dropped += 1;
      continue;
    }
    points.push([x, y, entry.pointIds?.[i] ?? entry.name]);
  }
  return { points, dropped };
}

export function buildScatterOption(args: BuildScatterOptionArgs): ScatterOptionModel {
  const fallbackColor = args.tokens.series[0] ?? UNRESOLVED_SERIES_COLOR;
  let droppedPointCount = 0;

  const series = args.series.map((entry, index) => {
    const { points, dropped } = plottable(entry);
    droppedPointCount += dropped;
    return {
      name: entry.name,
      points,
      color: args.tokens.series[index % args.tokens.series.length] ?? fallbackColor,
    };
  });

  const line =
    args.line === undefined
      ? null
      : {
          name: args.line.name,
          points: plottable(args.line).points,
          color: args.tokens.foreground,
        };

  return {
    series,
    line,
    xAxisName: args.xAxis.displayName,
    yAxisName: args.yAxis.displayName,
    droppedPointCount,
  };
}
