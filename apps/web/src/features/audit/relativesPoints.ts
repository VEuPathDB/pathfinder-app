import type { EvidenceView } from "@pathfinder/shared/generated/types/EvidenceView";
import type { FindingDetail } from "@pathfinder/shared/generated/types/FindingDetail";
import type { NoRelatives } from "@pathfinder/shared/generated/types/NoRelatives";
import type { Relative } from "@pathfinder/shared/generated/types/Relative";

import { EVIDENCE_STATUS_WORDS } from "./words";

export interface RelativesPoints {
  relatives: Relative[];
  model: number | null;
  reference: number | null;
  median: number | null;
}

export type RelativesOutcome =
  | { kind: "no_row" }
  | { kind: "not_read"; words: string }
  | { kind: "looked"; reason: string }
  | { kind: "plotted"; points: RelativesPoints };

const TOO_FEW =
  "Fewer than two genomes of other species in this genus, and fewer than two in other genera, have a length for the gene.";

const NO_RELATIVES_WORDS: Record<NoRelatives, string> = {
  RESIDUAL_GROUP: "The ortholog group is a residual group.",
  PARALOGS: "The related genomes do not hold one copy each.",
  FEWER_THAN_TWO: TOO_FEW,
};

function unreadWords(row: EvidenceView): string {
  const words = EVIDENCE_STATUS_WORDS[row.status];
  return row.status === "failed" && row.message !== null
    ? `${words}: ${row.message}`
    : words;
}

function byOrganism(left: Relative, right: Relative): number {
  return left.organism.localeCompare(right.organism);
}

export function relativesOutcome(detail: FindingDetail): RelativesOutcome {
  for (const row of detail.evidence) {
    const { payload } = row;
    if (row.kind === "relatives" && payload === null) {
      return { kind: "not_read", words: unreadWords(row) };
    }
    if (payload?.kind === "relatives") {
      const relatives = Object.entries(payload.relativeLengths)
        .map(([organism, length]) => ({ organism, length }))
        .sort(byOrganism);
      if (relatives.length === 0) {
        const reason =
          payload.referenceOrganism === null
            ? "The gene records hold no row of the reference gene, so no related genome was compared."
            : TOO_FEW;
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
        return { kind: "looked", reason: NO_RELATIVES_WORDS[missing] };
      }
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
