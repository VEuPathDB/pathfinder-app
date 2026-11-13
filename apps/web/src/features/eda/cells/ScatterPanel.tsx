"use client";

import type { EdaViz } from "@strategist/shared";

import { ScatterChart } from "@/lib/components/charts/ScatterChart";
import type { EdaScatterSeries } from "@/lib/components/charts/types";

import { formatEffectSize, READOUT_LIMIT } from "./vizReadout";

const CHART_HEIGHT = 260;
const Y_AXIS = "-log10(p-value)";

interface PlottedPoint {
  pointId: string;
  x: number;
  y: number;
}

function plottedPoints(payload: EdaViz): PlottedPoint[] {
  const rows: PlottedPoint[] = [];
  for (const point of payload.points) {
    if (point.pValue == null || point.pValue <= 0) continue;
    rows.push({
      pointId: point.pointId,
      x: point.effectSize,
      y: -Math.log10(point.pValue),
    });
  }
  return rows;
}

export function ScatterPanel({ payload }: { payload: EdaViz }) {
  const rows = plottedPoints(payload);
  const droppedCount = payload.points.length - rows.length;
  const series: EdaScatterSeries = {
    name: "Genes",
    x: rows.map((row) => row.x),
    y: rows.map((row) => row.y),
    pointIds: rows.map((row) => row.pointId),
  };

  return (
    <div className="flex flex-col gap-3 lg:flex-row">
      <div className="min-w-0 flex-1">
        <ScatterChart
          series={[series]}
          xAxis={{
            variableId: "effectSize",
            displayName: payload.effectSizeLabel,
          }}
          yAxis={{ variableId: "significance", displayName: Y_AXIS }}
          height={CHART_HEIGHT}
          testId="eda-viz-scatter"
        />
        {droppedCount > 0 ? (
          <p
            data-testid="eda-viz-scatter-no-pvalue"
            className="mt-1 text-[0.6875rem] text-muted-foreground"
          >
            {droppedCount === 1
              ? "1 point without a p-value was not plotted"
              : `${String(droppedCount)} points without a p-value were not plotted`}
          </p>
        ) : null}
      </div>
      <div className="w-full shrink-0 lg:w-80">
        <table
          data-testid="eda-viz-scatter-table"
          className="w-full text-left text-[0.6875rem]"
        >
          <thead className="text-muted-foreground">
            <tr>
              <th className="font-normal">Gene</th>
              <th className="font-normal">{payload.effectSizeLabel}</th>
              <th className="font-normal">{Y_AXIS}</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, READOUT_LIMIT).map((row) => (
              <tr key={row.pointId} data-testid={`eda-viz-scatter-row-${row.pointId}`}>
                <td className="pr-2 font-mono">{row.pointId}</td>
                <td className="pr-2">{formatEffectSize(row.x)}</td>
                <td>{formatEffectSize(row.y)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length > READOUT_LIMIT ? (
          <p
            data-testid="eda-viz-scatter-cap"
            className="mt-1 text-[0.6875rem] text-muted-foreground"
          >
            {`The first ${String(READOUT_LIMIT)} of ${String(rows.length)} plotted points are listed.`}
          </p>
        ) : null}
      </div>
    </div>
  );
}
