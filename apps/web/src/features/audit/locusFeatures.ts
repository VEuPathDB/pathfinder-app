import type { MissingGeneAudit } from "@pathfinder/shared/generated/types/MissingGeneAudit";

export interface LocusFeature {
  kind: "anchor" | "found" | "matched" | "overlap";
  label: string;
  start: number;
  end: number;
  strand: "+" | "-" | null;
}

export interface PlacedFeature extends LocusFeature {
  x: number;
  width: number;
}

export function locusFeatures(audit: MissingGeneAudit): LocusFeature[] {
  if (audit.anchors === null) return [];
  const { left, right } = audit.anchors;
  const located = audit.located;
  const span = located?.span ?? null;
  const encodes =
    audit.verdict === "IN_DNA_UNANNOTATED" || audit.verdict === "IN_DNA_OTHER_MODEL";
  return [
    ...[left, right].map((anchor): LocusFeature => ({
      kind: "anchor",
      label: anchor.gene,
      start: anchor.start,
      end: anchor.end,
      strand: anchor.strand,
    })),
    ...(span === null || located === null
      ? []
      : [
          {
            kind: encodes ? ("found" as const) : ("matched" as const),
            label: encodes
              ? `Where the DNA encodes ${audit.exampleGene}`
              : `${String(located.found)} of ${String(located.windows)} parts of the gene match`,
            start: span[0],
            end: span[1],
            strand: null,
          },
        ]),
    ...(audit.overlapping ?? []).map((gene): LocusFeature => ({
      kind: "overlap",
      label: gene.gene,
      start: gene.start,
      end: gene.end,
      strand: gene.strand,
    })),
  ];
}

export function placeLocus(
  features: LocusFeature[],
  width: number,
): { window: [number, number]; features: PlacedFeature[] } {
  const low = Math.min(...features.map((feature) => feature.start));
  const high = Math.max(...features.map((feature) => feature.end));
  const scale = width / Math.max(1, high - low);
  return {
    window: [low, high],
    features: features.map((feature) => ({
      ...feature,
      x: (feature.start - low) * scale,
      width: Math.max(1, (feature.end - feature.start) * scale),
    })),
  };
}
