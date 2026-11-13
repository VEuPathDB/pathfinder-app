import { useId } from "react";
import type { FindingModels } from "@strategist/shared/generated/types/FindingModels";

import { FIGURE_COLORS, FigureLegend } from "./FigureLegend";
import type { LegendEntry } from "./FigureLegend";
import { FIGURE_WIDTH, ModelRowDrawing, rowHeight } from "./GeneModelRow";
import type { ModelRow, Track } from "./geneModelTracks";
import { geneModelTracks } from "./geneModelTracks";
import { baseText, rowText } from "./geneModelWords";
import { ProteinFigure } from "./ProteinFigure";
import type { ProteinTrack } from "./proteinTracks";
import { tracksTitle } from "./proteinTracks";

const SCALE_ROOM = 20;
const MARGIN = 8;

function rowsHeight(rows: ModelRow[]): number {
  return rows.reduce((total, row) => total + rowHeight(row), 0);
}

function BaseScale({ window, top }: { window: Track["window"]; top: number }) {
  const [low, high] = window;
  return (
    <g data-part="scale" transform={`translate(0 ${String(top)})`}>
      <line x1="0" x2={FIGURE_WIDTH} y1="2" y2="2" stroke={FIGURE_COLORS.line} />
      <text x="0" y="13" fontSize="8" fill={FIGURE_COLORS.muted}>
        {baseText(low)}
      </text>
      <text
        x={FIGURE_WIDTH / 2}
        y="13"
        fontSize="8"
        textAnchor="middle"
        fill={FIGURE_COLORS.muted}
      >
        {`${baseText(high - low + 1)} bases`}
      </text>
      <text
        x={FIGURE_WIDTH}
        y="13"
        fontSize="8"
        textAnchor="end"
        fill={FIGURE_COLORS.muted}
      >
        {baseText(high)}
      </text>
    </g>
  );
}

function TrackDrawing({ track, hatch }: { track: Track; hatch: string }) {
  const id = useId();
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const [low, high] = track.window;
  const height = rowsHeight(track.rows);
  return (
    <svg
      role="img"
      aria-labelledby={`${titleId} ${descId}`}
      viewBox={`${String(-MARGIN)} 0 ${String(FIGURE_WIDTH + 2 * MARGIN)} ${String(height + SCALE_ROOM)}`}
      className="w-full"
    >
      <title id={titleId}>
        {`Gene models on ${track.seqid}, bases ${baseText(low)} to ${baseText(high)}`}
      </title>
      <desc id={descId}>
        {`Models drawn: ${track.rows.map((row) => row.label).join("; ")}`}
      </desc>
      {track.rows.map((row, index) => (
        <g
          key={row.label}
          data-row={row.label}
          transform={`translate(0 ${String(rowsHeight(track.rows.slice(0, index)))})`}
        >
          <ModelRowDrawing row={row} window={track.window} hatch={hatch} />
        </g>
      ))}
      <BaseScale window={track.window} top={height} />
    </svg>
  );
}

function legendEntries(rows: ModelRow[], hatch: string): LegendEntry[] {
  const has = (present: (row: ModelRow) => boolean) => rows.some(present);
  return [
    ...(has((row) => row.exons.length > 0)
      ? [{ word: "Exon", fill: "none", stroke: FIGURE_COLORS.ink }]
      : []),
    ...(has((row) => row.cds.length > 0)
      ? [{ word: "Coded part", fill: FIGURE_COLORS.coded }]
      : []),
    ...(has((row) => row.changed.length > 0)
      ? [
          {
            word: "Where the two models differ",
            fill: `url(#${hatch})`,
            stroke: FIGURE_COLORS.flagged,
          },
        ]
      : []),
    ...(has((row) => row.kept.length > 0)
      ? [
          {
            word: "Intron kept as exon",
            fill: FIGURE_COLORS.other,
            stroke: FIGURE_COLORS.ink,
          },
        ]
      : []),
    ...(has((row) => row.junctions.length > 0)
      ? [{ word: "RNA-seq junction", fill: "none", stroke: FIGURE_COLORS.other }]
      : []),
    ...(has((row) => row.span !== null)
      ? [{ word: "Merged model's span", fill: "none", stroke: FIGURE_COLORS.ink }]
      : []),
    ...(has((row) => row.stop.length > 0)
      ? [{ word: "The model's last coded codon", fill: FIGURE_COLORS.flagged }]
      : []),
  ];
}

export function GeneModelFigure({
  models,
  proteinTracks,
}: {
  models: FindingModels;
  proteinTracks: ProteinTrack[];
}) {
  const hatch = `hatch${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const tracks = geneModelTracks(models);
  const rows = tracks.flatMap((track) => track.rows);
  return (
    <div className="mt-3 text-xs">
      <figure>
        <svg width="0" height="0" aria-hidden="true" className="absolute">
          <defs>
            <pattern
              id={hatch}
              width="6"
              height="6"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <line x1="0" y1="0" x2="0" y2="6" stroke={FIGURE_COLORS.flagged} />
            </pattern>
          </defs>
        </svg>
        <div className="space-y-3">
          {tracks.map((track) => (
            <TrackDrawing key={track.seqid} track={track} hatch={hatch} />
          ))}
        </div>
        <figcaption className="mt-1 text-muted-foreground">
          <ul className="space-y-0.5">
            {rows.map((row) => (
              <li key={row.label}>{rowText(row)}</li>
            ))}
          </ul>
          <FigureLegend entries={legendEntries(rows, hatch)} />
        </figcaption>
      </figure>
      <ProteinFigure
        title={tracksTitle(models.kind === "pseudogene")}
        tracks={proteinTracks}
      />
    </div>
  );
}
