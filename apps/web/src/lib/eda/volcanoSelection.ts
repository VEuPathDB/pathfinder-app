import type {
  VolcanoPointInput,
  VolcanoThresholds,
} from "@/lib/components/charts/types";

export interface VolcanoSelection {
  up: string[];
  down: string[];
  selected: string[];
  droppedRowCount: number;
}

function finite(raw: number | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;
  return Number.isFinite(raw) ? raw : null;
}

/** The genes WDK's step returns: |effect| >= the effect cut, raw p <= the p cut. */
export function selectVolcanoGenes(
  points: readonly VolcanoPointInput[],
  thresholds: VolcanoThresholds,
): VolcanoSelection {
  const up: string[] = [];
  const down: string[] = [];
  let droppedRowCount = 0;

  for (const point of points) {
    const effect = finite(point.effectSize);
    const significance = finite(point.pValue);
    if (effect === null || significance === null) {
      droppedRowCount += 1;
      continue;
    }
    if (Math.abs(effect) < thresholds.effectSizeThreshold) continue;
    if (significance > thresholds.significanceThreshold) continue;
    if (effect > 0) up.push(point.pointId);
    else down.push(point.pointId);
  }

  const selected =
    thresholds.direction === "upOnly"
      ? [...up]
      : thresholds.direction === "downOnly"
        ? [...down]
        : [...up, ...down];
  return { up, down, selected, droppedRowCount };
}
