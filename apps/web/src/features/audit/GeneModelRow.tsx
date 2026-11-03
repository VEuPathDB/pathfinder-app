import { FIGURE_COLORS } from "./FigureLegend";
import type { Box, ModelRow, Track } from "./geneModelTracks";
import { placeBox } from "./geneModelTracks";
import { readsText } from "./geneModelWords";

export const FIGURE_WIDTH = 600;
const ROW = 36;
const JUNCTION_ROOM = 14;
const BOX_TOP = 14;
const BOX_HEIGHT = 14;
const BOX_MIDDLE = BOX_TOP + BOX_HEIGHT / 2;
const BAND_TOP = 11;
const BAND_HEIGHT = 20;
const ARROW = 6;

function one(value: number): string {
  return value.toFixed(1);
}

export function rowHeight(row: ModelRow): number {
  return row.junctions.length === 0 ? ROW : ROW + JUNCTION_ROOM;
}

interface BoxPartProps {
  part: string;
  box: Box;
  window: Track["window"];
  top: number;
  height: number;
  fill: string;
  stroke?: string;
  strokeDasharray?: string;
}

function BoxPart({ part, box, window, top, height, ...paint }: BoxPartProps) {
  const placed = placeBox(box, window, FIGURE_WIDTH);
  return (
    <rect
      data-part={part}
      x={one(placed.x)}
      y={top}
      width={one(placed.width)}
      height={height}
      {...paint}
    />
  );
}

function StrandArrow({ row, window }: { row: ModelRow; window: Track["window"] }) {
  const ends = [...row.exons, ...(row.span === null ? [] : [row.span])];
  const [low, high] = [
    Math.min(...ends.map((box) => box.start)),
    Math.max(...ends.map((box) => box.end)),
  ];
  const placed = placeBox({ start: low, end: high }, window, FIGURE_WIDTH);
  const forward = row.strand === "+";
  const tip = forward ? placed.x + placed.width + ARROW : placed.x - ARROW;
  const base = forward ? placed.x + placed.width : placed.x;
  const points = [
    `${one(base)},${String(BOX_TOP)}`,
    `${one(tip)},${String(BOX_MIDDLE)}`,
    `${one(base)},${String(BOX_TOP + BOX_HEIGHT)}`,
  ].join(" ");
  return (
    <polygon
      data-part="strand"
      data-strand={row.strand}
      points={points}
      fill={FIGURE_COLORS.muted}
    />
  );
}

function Junction({
  junction,
  window,
}: {
  junction: ModelRow["junctions"][number];
  window: Track["window"];
}) {
  const placed = placeBox(junction.box, window, FIGURE_WIDTH);
  const middle = placed.x + placed.width / 2;
  const floor = BOX_TOP + BOX_HEIGHT;
  return (
    <g data-part="junction">
      <path
        d={`M ${one(placed.x)} ${String(floor)} Q ${one(middle)} ${String(floor + 16)} ${one(placed.x + placed.width)} ${String(floor)}`}
        fill="none"
        stroke={FIGURE_COLORS.other}
        strokeWidth="1.5"
      />
      <text
        x={one(middle)}
        y={floor + JUNCTION_ROOM + 3}
        fontSize="8"
        textAnchor="middle"
        fill={FIGURE_COLORS.muted}
      >
        {readsText(junction.reads)}
      </text>
    </g>
  );
}

export function ModelRowDrawing({
  row,
  window,
  hatch,
}: {
  row: ModelRow;
  window: Track["window"];
  hatch: string;
}) {
  return (
    <>
      <text x="0" y="9" fontSize="9" fill={FIGURE_COLORS.muted}>
        {row.label}
      </text>
      {row.changed.map((box) => (
        <BoxPart
          key={`changed-${String(box.start)}`}
          part="changed"
          box={box}
          window={window}
          top={BAND_TOP}
          height={BAND_HEIGHT}
          fill={`url(#${hatch})`}
        />
      ))}
      {row.introns.map((box) => {
        const placed = placeBox(box, window, FIGURE_WIDTH);
        return (
          <line
            key={`intron-${String(box.start)}`}
            data-part="intron"
            x1={one(placed.x)}
            x2={one(placed.x + placed.width)}
            y1={BOX_MIDDLE}
            y2={BOX_MIDDLE}
            stroke={FIGURE_COLORS.muted}
          />
        );
      })}
      {row.exons.map((box) => (
        <BoxPart
          key={`exon-${String(box.start)}`}
          part="exon"
          box={box}
          window={window}
          top={BOX_TOP}
          height={BOX_HEIGHT}
          fill="none"
          stroke={FIGURE_COLORS.ink}
        />
      ))}
      {row.cds.map((box) => (
        <BoxPart
          key={`cds-${String(box.start)}`}
          part="cds"
          box={box}
          window={window}
          top={BOX_TOP}
          height={BOX_HEIGHT}
          fill={FIGURE_COLORS.coded}
        />
      ))}
      {row.kept.map((box) => (
        <BoxPart
          key={`kept-${String(box.start)}`}
          part="kept"
          box={box}
          window={window}
          top={BOX_TOP}
          height={BOX_HEIGHT}
          fill={FIGURE_COLORS.other}
          stroke={FIGURE_COLORS.ink}
        />
      ))}
      {row.span === null ? null : (
        <BoxPart
          part="span"
          box={row.span}
          window={window}
          top={BOX_TOP}
          height={BOX_HEIGHT}
          fill="none"
          stroke={FIGURE_COLORS.ink}
          strokeDasharray="4 3"
        />
      )}
      {row.stop.map((box) => (
        <BoxPart
          key={`stop-${String(box.start)}`}
          part="stop"
          box={box}
          window={window}
          top={BAND_TOP}
          height={BAND_HEIGHT}
          fill={FIGURE_COLORS.flagged}
        />
      ))}
      {row.stop[0] === undefined ? null : (
        <text
          x={one(placeBox(row.stop[0], window, FIGURE_WIDTH).x)}
          y={BAND_TOP + BAND_HEIGHT + 5}
          fontSize="8"
          textAnchor="middle"
          fill={FIGURE_COLORS.ink}
        >
          last codon
        </text>
      )}
      {row.junctions.map((junction) => (
        <Junction
          key={`junction-${String(junction.box.start)}`}
          junction={junction}
          window={window}
        />
      ))}
      <StrandArrow row={row} window={window} />
    </>
  );
}
