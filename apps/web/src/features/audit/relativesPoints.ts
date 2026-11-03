import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";
import type { Relative } from "@pathfinder/shared/generated/types/Relative";

export interface RelativesPoints {
  relatives: Relative[];
  model: number | null;
  reference: number | null;
  median: number | null;
}

function byOrganism(left: Relative, right: Relative): number {
  return left.organism.localeCompare(right.organism);
}

export function relativesPoints(detail: FindingDetail): RelativesPoints | null {
  for (const { payload } of detail.evidence) {
    if (payload?.kind === "relatives") {
      const relatives = Object.entries(payload.relativeLengths)
        .map(([organism, length]) => ({ organism, length }))
        .sort(byOrganism);
      if (relatives.length === 0) return null;
      return {
        relatives,
        model: payload.modelLength,
        reference: payload.referenceLength,
        median: payload.relativesMedian,
      };
    }
    if (
      payload?.kind === "confirmation" &&
      payload.confirmation.check === "strain_model"
    ) {
      const { result } = payload.confirmation;
      if (result.relatives.members.length === 0) return null;
      return {
        relatives: [...result.relatives.members].sort(byOrganism),
        model: result.strainLength,
        reference: result.referenceLength,
        median: result.relatives.median,
      };
    }
  }
  return null;
}

export function pointLengths(points: RelativesPoints): number[] {
  return [
    ...points.relatives.map((dot) => dot.length),
    ...[points.model, points.reference, points.median].filter(
      (length) => length !== null,
    ),
  ];
}

export function stripX(length: number, lengths: number[], width: number): number {
  const low = Math.min(...lengths);
  const span = Math.max(...lengths) - low;
  return span === 0 ? width / 2 : ((length - low) / span) * width;
}
