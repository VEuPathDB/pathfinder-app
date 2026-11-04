import { FIGURE_COLORS, FigureLegend } from "./FigureLegend";
import type { LegendEntry } from "./FigureLegend";
import type { RelativesOutcome, RelativesPoints } from "./relativesPoints";
import { pointLengths, stripX } from "./relativesPoints";

const WIDTH = 600;
const MARGIN = 10;
const LEAST_AXIS = 34;
const BELOW_AXIS = 20;
const DOT = 4;
const DIAMOND = DOT + 1;
const STACK = 9;

function residues(length: number): string {
  return `${length.toLocaleString("en-US")} residues`;
}

function statedLabel(points: RelativesPoints): string {
  const marked = [
    ...(points.model === null ? [] : [`this model ${residues(points.model)}`]),
    ...(points.reference === null ? [] : [`reference ${residues(points.reference)}`]),
    ...(points.median === null ? [] : [`median ${residues(points.median)}`]),
  ];
  const relatives = points.relatives.map(
    (dot) => `${dot.organism} ${residues(dot.length)}`,
  );
  return `Protein lengths: ${[...marked, ...relatives].join(", ")}`;
}

function listedLengths(points: RelativesPoints): [string, number][] {
  const marked: [string, number | null][] = [
    ["This model", points.model],
    ["Reference", points.reference],
    ["Median of the related genomes", points.median],
  ];
  return [
    ...marked.flatMap(([name, length]): [string, number][] =>
      length === null ? [] : [[name, length]],
    ),
    ...points.relatives.map((dot): [string, number] => [dot.organism, dot.length]),
  ];
}

function stackedDots(points: RelativesPoints): { length: number; rank: number }[] {
  const lengths = points.relatives.map((dot) => dot.length).sort((a, b) => a - b);
  return lengths.map((length, index) => ({
    length,
    rank: lengths.slice(0, index).filter((other) => other === length).length,
  }));
}

function legendEntries(points: RelativesPoints): LegendEntry[] {
  return [
    { word: "Related genome", fill: FIGURE_COLORS.coded },
    ...(points.model === null
      ? []
      : [{ word: "This model", fill: FIGURE_COLORS.flagged }]),
    ...(points.reference === null
      ? []
      : [{ word: "Reference", fill: "none", stroke: FIGURE_COLORS.other }]),
    ...(points.median === null
      ? []
      : [{ word: "Median", fill: "none", stroke: FIGURE_COLORS.ink }]),
  ];
}

function Strip({ points }: { points: RelativesPoints }) {
  const lengths = pointLengths(points);
  const at = (length: number) => stripX(length, lengths, WIDTH);
  const dots = stackedDots(points);
  const highest = Math.max(...dots.map((dot) => dot.rank));
  const axis = Math.max(LEAST_AXIS, highest * STACK + DOT + 2);
  return (
    <svg
      role="img"
      aria-label={statedLabel(points)}
      viewBox={`${String(-MARGIN)} 0 ${String(WIDTH + 2 * MARGIN)} ${String(axis + BELOW_AXIS)}`}
      className="w-full"
    >
      <line x1="0" x2={WIDTH} y1={axis} y2={axis} stroke={FIGURE_COLORS.line} />
      <text x="0" y={axis + 16} fontSize="9" fill={FIGURE_COLORS.muted}>
        {residues(Math.min(...lengths))}
      </text>
      <text
        x={WIDTH}
        y={axis + 16}
        fontSize="9"
        textAnchor="end"
        fill={FIGURE_COLORS.muted}
      >
        {residues(Math.max(...lengths))}
      </text>
      {points.median === null ? null : (
        <line
          data-part="median"
          x1={at(points.median).toFixed(1)}
          x2={at(points.median).toFixed(1)}
          y1="4"
          y2={axis + 6}
          stroke={FIGURE_COLORS.ink}
          strokeDasharray="3 2"
        />
      )}
      {dots.map(({ length, rank }) => (
        <circle
          key={`${String(length)}-${String(rank)}`}
          data-part="relative"
          cx={at(length).toFixed(1)}
          cy={axis - rank * STACK}
          r={DOT}
          fill={FIGURE_COLORS.coded}
        />
      ))}
      {points.reference === null ? null : (
        <rect
          data-part="reference"
          x={(at(points.reference) - DOT).toFixed(1)}
          y={axis - DOT}
          width={2 * DOT}
          height={2 * DOT}
          fill="none"
          stroke={FIGURE_COLORS.other}
          strokeWidth="2"
        />
      )}
      {points.model === null ? null : (
        <polygon
          data-part="model"
          points={[
            [at(points.model), axis - DIAMOND],
            [at(points.model) + DIAMOND, axis],
            [at(points.model), axis + DIAMOND],
            [at(points.model) - DIAMOND, axis],
          ]
            .map(([x = 0, y = 0]) => `${x.toFixed(1)},${String(y)}`)
            .join(" ")}
          fill={FIGURE_COLORS.flagged}
        />
      )}
    </svg>
  );
}

export function RelativesPlot({ outcome }: { outcome: RelativesOutcome }) {
  switch (outcome.kind) {
    case "no_row":
      return null;
    case "looked":
      return <p className="text-xs text-muted-foreground">{outcome.reason}</p>;
    case "plotted":
      return (
        <figure className="mt-3 text-xs">
          <Strip points={outcome.points} />
          <figcaption className="mt-1 text-muted-foreground">
            <ul className="space-y-0.5">
              {listedLengths(outcome.points).map(([name, length]) => (
                <li key={name}>{`${name}: ${residues(length)}`}</li>
              ))}
            </ul>
            <FigureLegend entries={legendEntries(outcome.points)} />
          </figcaption>
        </figure>
      );
  }
}
