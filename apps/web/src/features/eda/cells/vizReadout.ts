import type { EdaVolcanoPoint } from "@strategist/shared/generated/types/EdaVolcanoPoint";

/** A read-out lists at most this many rows; a volcano can select thousands. */
export const READOUT_LIMIT = 50;

export function formatEffectSize(value: number): string {
  return value.toFixed(2);
}

export function formatPValue(value: number | null | undefined): string {
  return value == null ? "none" : value.toExponential(2);
}

export function pointsById(
  points: readonly EdaVolcanoPoint[],
): Map<string, EdaVolcanoPoint> {
  return new Map(points.map((point) => [point.pointId, point]));
}
