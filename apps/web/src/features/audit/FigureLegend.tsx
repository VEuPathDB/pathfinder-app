export const FIGURE_COLORS = {
  ink: "hsl(var(--foreground))",
  muted: "hsl(var(--muted-foreground))",
  line: "hsl(var(--border))",
  coded: "hsl(var(--chart-1))",
  other: "hsl(var(--chart-2))",
  found: "hsl(var(--chart-positive))",
  overlap: "hsl(var(--chart-5))",
  matched: "hsl(var(--chart-3))",
  flagged: "hsl(var(--chart-negative))",
} as const;

export interface LegendEntry {
  word: string;
  fill: string;
  stroke?: string;
}

export function FigureLegend({ entries }: { entries: LegendEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
      {entries.map((entry) => (
        <span key={entry.word} className="inline-flex items-center gap-1">
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <rect
              x="1"
              y="1"
              width="10"
              height="10"
              fill={entry.fill}
              stroke={entry.stroke ?? "none"}
            />
          </svg>
          <span>{entry.word}</span>
        </span>
      ))}
    </div>
  );
}
