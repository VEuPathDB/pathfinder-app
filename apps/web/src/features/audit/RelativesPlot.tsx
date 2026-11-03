import { FIGURE_COLORS, FigureLegend } from "./FigureLegend";
import type { RelativesPoints } from "./relativesPoints";
import { pointLengths, stripX } from "./relativesPoints";

const WIDTH = 600;
const MARGIN = 10;
const AXIS = 34;
const DOT = 4;
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
  return [
    ...(points.model === null
      ? []
      : [["This model", points.model] as [string, number]]),
    ...(points.reference === null
      ? []
      : [["Reference", points.reference] as [string, number]]),
    ...(points.median === null
      ? []
      : [["Median of the related genomes", points.median] as [string, number]]),
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

export function RelativesPlot({ points }: { points: RelativesPoints | null }) {
  if (points === null) {
    return (
      <p className="text-xs text-muted-foreground">{"Relatives' lengths not stored"}</p>
    );
  }
  const lengths = pointLengths(points);
  const at = (length: number) => stripX(length, lengths, WIDTH);
  const low = Math.min(...lengths);
  const high = Math.max(...lengths);
  return (
    <figure className="mt-3 text-xs">
      <svg
        role="img"
        aria-label={statedLabel(points)}
        viewBox={`${String(-MARGIN)} 0 ${String(WIDTH + 2 * MARGIN)} 54`}
        className="w-full"
      >
        <line x1="0" x2={WIDTH} y1={AXIS} y2={AXIS} stroke={FIGURE_COLORS.line} />
        <text x="0" y="50" fontSize="9" fill={FIGURE_COLORS.muted}>
          {residues(low)}
        </text>
        <text x={WIDTH} y="50" fontSize="9" textAnchor="end" fill={FIGURE_COLORS.muted}>
          {residues(high)}
        </text>
        {points.median === null ? null : (
          <line
            data-part="median"
            x1={at(points.median).toFixed(1)}
            x2={at(points.median).toFixed(1)}
            y1="4"
            y2={AXIS + 6}
            stroke={FIGURE_COLORS.ink}
            strokeDasharray="3 2"
          />
        )}
        {stackedDots(points).map(({ length, rank }) => (
          <circle
            key={`${String(length)}-${String(rank)}`}
            data-part="relative"
            cx={at(length).toFixed(1)}
            cy={AXIS - rank * STACK}
            r={DOT}
            fill={FIGURE_COLORS.coded}
          />
        ))}
        {points.reference === null ? null : (
          <rect
            data-part="reference"
            data-x={at(points.reference).toFixed(1)}
            x={(at(points.reference) - DOT).toFixed(1)}
            y={AXIS - DOT}
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
            data-x={at(points.model).toFixed(1)}
            points={[
              [at(points.model), AXIS - DOT - 1],
              [at(points.model) + DOT + 1, AXIS],
              [at(points.model), AXIS + DOT + 1],
              [at(points.model) - DOT - 1, AXIS],
            ]
              .map(([x, y]) => `${String(x)},${String(y)}`)
              .join(" ")}
            fill={FIGURE_COLORS.flagged}
          />
        )}
      </svg>
      <figcaption className="mt-1 text-muted-foreground">
        <ul className="space-y-0.5">
          {listedLengths(points).map(([name, length]) => (
            <li key={name}>{`${name}: ${residues(length)}`}</li>
          ))}
        </ul>
        <FigureLegend
          entries={[
            { word: "Related genome", fill: FIGURE_COLORS.coded },
            { word: "This model", fill: FIGURE_COLORS.flagged },
            { word: "Reference", fill: "none", stroke: FIGURE_COLORS.other },
            { word: "Median", fill: "none", stroke: FIGURE_COLORS.ink },
          ]}
        />
      </figcaption>
    </figure>
  );
}
