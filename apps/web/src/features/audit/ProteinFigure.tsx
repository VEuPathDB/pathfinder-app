import { useId } from "react";

import { FIGURE_COLORS, FigureLegend } from "./FigureLegend";
import { joinWords } from "./format";
import type { ProteinMark, ProteinMarkKind, ProteinTrack } from "./proteinTracks";
import { placeTracks } from "./proteinTracks";

const WIDTH = 600;
const ROW = 28;
const BAR_TOP = 12;
const BAR_HEIGHT = 12;

const MARK_WORDS: Record<ProteinMarkKind, string> = {
  missing: "missing from the other model",
  extra: "only in this model",
  stop: "stop codon",
  peptide: "mass-spec peptide",
  structure: "AlphaFold structure",
};

const MARK_COLORS: Record<ProteinMarkKind, string> = {
  missing: FIGURE_COLORS.flagged,
  extra: FIGURE_COLORS.other,
  stop: FIGURE_COLORS.flagged,
  peptide: FIGURE_COLORS.coded,
  structure: FIGURE_COLORS.muted,
};

const MARK_KINDS: ProteinMarkKind[] = [
  "structure",
  "peptide",
  "missing",
  "extra",
  "stop",
];

function runText(mark: ProteinMark): string {
  const first = mark.first.toLocaleString("en-US");
  return mark.first === mark.last
    ? first
    : `${first} to ${mark.last.toLocaleString("en-US")}`;
}

function kindText(
  kind: ProteinMarkKind,
  marks: ProteinMark[],
  stopsCut: boolean,
): string {
  const single = marks.length === 1 && marks[0]?.first === marks[0]?.last;
  return `${MARK_WORDS[kind]}: ${single ? "residue" : "residues"} ${joinWords(marks.map(runText))}${
    kind === "stop" && stopsCut ? ` (the first ${String(marks.length)})` : ""
  }`;
}

function trackText(track: ProteinTrack): string {
  const stated = MARK_KINDS.flatMap((kind) => {
    const marks = track.marks.filter((mark) => mark.kind === kind);
    return marks.length === 0 ? [] : [kindText(kind, marks, track.stopsCut)];
  });
  return [track.summary, ...stated].join("; ");
}

export function ProteinFigure({
  title,
  tracks,
}: {
  title: string;
  tracks: ProteinTrack[];
}) {
  const id = useId();
  if (tracks.length === 0) return null;
  const titleId = `${id}-title`;
  const descId = `${id}-desc`;
  const drawn = MARK_KINDS.filter((kind) =>
    tracks.some((track) => track.marks.some((mark) => mark.kind === kind)),
  );
  return (
    <figure className="mt-3 text-xs">
      <svg
        role="img"
        aria-labelledby={`${titleId} ${descId}`}
        viewBox={`0 0 ${String(WIDTH)} ${String(ROW * tracks.length + 8)}`}
        className="w-full"
      >
        <title id={titleId}>{title}</title>
        <desc id={descId}>{tracks.map(trackText).join(". ")}</desc>
        {placeTracks(tracks, WIDTH).map((track, index) => (
          <g key={track.label} transform={`translate(0 ${String(index * ROW)})`}>
            <text x="0" y="9" fontSize="9" fill={FIGURE_COLORS.muted}>
              {track.label}
            </text>
            <rect
              x="0"
              y={BAR_TOP}
              width={track.width.toFixed(1)}
              height={BAR_HEIGHT}
              fill="none"
              stroke={FIGURE_COLORS.line}
            />
            {track.marks.map((mark) => (
              <rect
                key={`${mark.kind}-${String(mark.first)}-${String(mark.last)}`}
                data-kind={mark.kind}
                x={mark.x.toFixed(1)}
                y={BAR_TOP}
                width={mark.width.toFixed(1)}
                height={BAR_HEIGHT}
                fill={MARK_COLORS[mark.kind]}
                fillOpacity={mark.kind === "structure" ? 0.25 : 0.85}
              />
            ))}
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 text-muted-foreground">
        <ul className="space-y-0.5">
          {tracks.map((track) => (
            <li key={track.label}>{trackText(track)}</li>
          ))}
        </ul>
        <FigureLegend
          entries={drawn.map((kind) => ({
            word: MARK_WORDS[kind],
            fill: MARK_COLORS[kind],
          }))}
        />
      </figcaption>
    </figure>
  );
}
