"use client";

import type { EdaViz } from "@pathfinder/shared";
import type { EdaComparison } from "@pathfinder/shared/generated/types/EdaComparison";

import type { VolcanoThresholds } from "@/lib/components/charts/types";
import { VolcanoChart } from "@/lib/components/charts/VolcanoChart";
import { higherIn } from "@/lib/eda/comparison";
import { selectVolcanoGenes } from "@/lib/eda/volcanoSelection";
import { useEdaStore } from "@/state/eda";

import {
  formatEffectSize,
  formatPValue,
  pointsById,
  READOUT_LIMIT,
} from "./vizReadout";

const CHART_HEIGHT = 260;

function sideOf(
  thresholds: VolcanoThresholds,
  comparison: EdaComparison | null | undefined,
): string {
  switch (thresholds.direction) {
    case "upAndDown":
      return "Higher in either group";
    case "upOnly":
      return higherIn(comparison, "B");
    case "downOnly":
      return higherIn(comparison, "A");
  }
}

/** The cut the analysis stores, in words. The site's volcano cell edits it. */
function cutSentence(
  thresholds: VolcanoThresholds,
  comparison: EdaComparison | null | undefined,
): string {
  return `${sideOf(thresholds, comparison)}, |effect size| >= ${String(thresholds.effectSizeThreshold)}, p <= ${String(thresholds.significanceThreshold)}`;
}

export function VolcanoPanel({ payload }: { payload: EdaViz }) {
  const thresholds = useEdaStore((s) => s.volcanoThresholds);
  const points = payload.points;
  const selection = selectVolcanoGenes(points, thresholds);
  const byId = pointsById(points);
  const listed = selection.selected.slice(0, READOUT_LIMIT);

  return (
    <div className="space-y-3">
      <p data-testid="eda-volcano-cut" className="text-xs text-muted-foreground">
        {cutSentence(thresholds, payload.comparison)}
      </p>
      <div className="flex flex-col gap-3 lg:flex-row">
        <div className="min-w-0 flex-1">
          <VolcanoChart
            points={points}
            thresholds={thresholds}
            effectSizeLabel={payload.effectSizeLabel}
            comparison={payload.comparison}
            height={CHART_HEIGHT}
            testId="eda-viz-volcano"
          />
        </div>
        <div className="w-full shrink-0 lg:w-80">
          <p
            data-testid="eda-volcano-selection"
            className="text-xs text-muted-foreground"
          >
            {`${String(selection.selected.length)} ${selection.selected.length === 1 ? "gene" : "genes"} selected, ${String(payload.retainedPoints)} of ${String(payload.totalPoints)} retained by the comparison`}
          </p>
          <table className="mt-2 w-full text-left text-[11px]">
            <thead className="text-muted-foreground">
              <tr>
                <th className="font-normal">Gene</th>
                <th className="font-normal">Effect</th>
                <th className="font-normal">p</th>
              </tr>
            </thead>
            <tbody>
              {listed.map((pointId) => {
                const point = byId.get(pointId);
                return (
                  <tr key={pointId} data-testid={`eda-volcano-gene-${pointId}`}>
                    <td className="pr-2 font-mono">{pointId}</td>
                    <td className="pr-2">
                      {point === undefined ? "" : formatEffectSize(point.effectSize)}
                    </td>
                    <td>{point === undefined ? "" : formatPValue(point.pValue)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {selection.selected.length > READOUT_LIMIT ? (
            <p
              data-testid="eda-volcano-readout-cap"
              className="mt-1 text-[11px] text-muted-foreground"
            >
              {`The first ${String(READOUT_LIMIT)} of ${String(selection.selected.length)} selected genes are listed.`}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
