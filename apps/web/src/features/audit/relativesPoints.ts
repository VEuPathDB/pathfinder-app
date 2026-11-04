import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";
import type { Relative } from "@pathfinder/shared/generated/types/Relative";

export interface RelativesPoints {
  relatives: Relative[];
  model: number | null;
  reference: number | null;
  median: number | null;
}

export type RelativesOutcome =
  | { kind: "no_row" }
  | { kind: "looked"; reason: string }
  | { kind: "plotted"; points: RelativesPoints };

function byOrganism(left: Relative, right: Relative): number {
  return left.organism.localeCompare(right.organism);
}

export function relativesOutcome(
  detail: FindingDetail,
  words: AuditWords,
): RelativesOutcome {
  for (const { status, payload } of detail.evidence) {
    if (status !== "stored") continue;
    if (payload?.kind === "relatives") {
      const relatives = Object.entries(payload.relativeLengths)
        .map(([organism, length]) => ({ organism, length }))
        .sort(byOrganism);
      if (relatives.length === 0) {
        const reason =
          payload.referenceOrganism === null
            ? "The gene records hold no row of the reference gene, so no related genome was compared."
            : words.noRelatives.FEWER_THAN_TWO;
        return { kind: "looked", reason };
      }
      return {
        kind: "plotted",
        points: {
          relatives,
          model: payload.modelLength,
          reference: payload.referenceLength,
          median: payload.relativesMedian,
        },
      };
    }
    if (
      payload?.kind === "confirmation" &&
      payload.confirmation.check === "strain_model"
    ) {
      const { result } = payload.confirmation;
      const { members, missing, median } = result.relatives;
      if (missing !== null) {
        return { kind: "looked", reason: words.noRelatives[missing] };
      }
      if (members.length === 0) return { kind: "no_row" };
      return {
        kind: "plotted",
        points: {
          relatives: [...members].sort(byOrganism),
          model: result.strainLength,
          reference: result.referenceLength,
          median,
        },
      };
    }
  }
  return { kind: "no_row" };
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
