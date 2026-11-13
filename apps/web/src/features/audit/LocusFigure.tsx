import { useId } from "react";
import type { MissingGeneAudit } from "@strategist/shared/generated/types/MissingGeneAudit";

import { FIGURE_COLORS, FigureLegend } from "./FigureLegend";
import { baseText } from "./geneModelWords";
import type { LocusFeature, PlacedFeature } from "./locusFeatures";
import { locusFeatures, placeLocus } from "./locusFeatures";

const WIDTH = 600;
const ROW = 22;
const BOX_TOP = 10;
const BOX_HEIGHT = 10;
const ARROW = 5;
const MARGIN = 8;

const FEATURE_COLORS: Record<LocusFeature["kind"], string> = {
  anchor: FIGURE_COLORS.muted,
  found: FIGURE_COLORS.found,
  matched: FIGURE_COLORS.matched,
  overlap: FIGURE_COLORS.overlap,
};

const FEATURE_WORDS: Record<LocusFeature["kind"], string> = {
  anchor: "Conserved neighbour",
  found: "Where the DNA encodes the gene",
  matched: "Parts of the gene that match",
  overlap: "Gene model over the span",
};

const FEATURE_KINDS: LocusFeature["kind"][] = ["anchor", "found", "matched", "overlap"];

function featureText(feature: LocusFeature): string {
  if (feature.kind === "matched") {
    return `${feature.label}, first to last at bases ${baseText(feature.start)} to ${baseText(feature.end)}`;
  }
  const strand = feature.strand === null ? "" : `, ${feature.strand} strand`;
  return `${feature.label}${strand}: bases ${baseText(feature.start)} to ${baseText(feature.end)}`;
}

function FeatureDrawing({ feature }: { feature: PlacedFeature }) {
  const end = feature.x + feature.width;
  const middle = BOX_TOP + BOX_HEIGHT / 2;
  const fill = FEATURE_COLORS[feature.kind];
  return (
    <>
      <text x={feature.x.toFixed(1)} y="8" fontSize="8" fill={FIGURE_COLORS.muted}>
        {feature.label}
      </text>
      <rect
        data-part={feature.kind}
        x={feature.x.toFixed(1)}
        y={BOX_TOP}
        width={feature.width.toFixed(1)}
        height={BOX_HEIGHT}
        {...(feature.kind === "matched"
          ? { fill: "none", stroke: fill, strokeDasharray: "4 3" }
          : { fill })}
      />
      {feature.strand === null ? null : (
        <polygon
          data-part="strand"
          data-strand={feature.strand}
          points={
            feature.strand === "+"
              ? `${end.toFixed(1)},${String(BOX_TOP)} ${(end + ARROW).toFixed(1)},${String(middle)} ${end.toFixed(1)},${String(BOX_TOP + BOX_HEIGHT)}`
              : `${feature.x.toFixed(1)},${String(BOX_TOP)} ${(feature.x - ARROW).toFixed(1)},${String(middle)} ${feature.x.toFixed(1)},${String(BOX_TOP + BOX_HEIGHT)}`
          }
          fill={fill}
        />
      )}
    </>
  );
}

export function LocusFigure({ audit }: { audit: MissingGeneAudit }) {
  const id = useId();
  const features = locusFeatures(audit);
  if (audit.anchors === null) return null;
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const placed = placeLocus(features, WIDTH);
  const [low, high] = placed.window;
  return (
    <figure className="mt-3 text-xs">
      <svg
        role="img"
        aria-labelledby={`${titleId} ${descId}`}
        viewBox={`${String(-MARGIN)} 0 ${String(WIDTH + 2 * MARGIN)} ${String(ROW * features.length + 4)}`}
        className="w-full"
      >
        <title id={titleId}>
          {`The locus of ${audit.exampleGene} in ${audit.absentOrganism} on ${audit.anchors.left.sequenceId}, bases ${baseText(low)} to ${baseText(high)}`}
        </title>
        <desc id={descId}>{features.map((feature) => feature.label).join("; ")}</desc>
        {placed.features.map((feature, index) => (
          <g key={feature.label} transform={`translate(0 ${String(index * ROW)})`}>
            <FeatureDrawing feature={feature} />
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 text-muted-foreground">
        <ul className="space-y-0.5">
          {features.map((feature) => (
            <li key={feature.label}>{featureText(feature)}</li>
          ))}
        </ul>
        <FigureLegend
          entries={FEATURE_KINDS.filter((kind) =>
            features.some((feature) => feature.kind === kind),
          ).map((kind) =>
            kind === "matched"
              ? {
                  word: FEATURE_WORDS[kind],
                  fill: "none",
                  stroke: FEATURE_COLORS[kind],
                }
              : { word: FEATURE_WORDS[kind], fill: FEATURE_COLORS[kind] },
          )}
        />
      </figcaption>
    </figure>
  );
}
