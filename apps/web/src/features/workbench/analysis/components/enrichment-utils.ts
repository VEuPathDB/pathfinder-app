import type { EnrichmentTerm } from "@pathfinder/shared";
import { hslFromTriple, hslTriple } from "@/lib/color/hsl";

export type SortKey = "termName" | "geneCount" | "foldEnrichment" | "pValue" | "fdr";

export const MAX_CHART_TERMS = 15;
export const DOT_MIN_R = 4;
export const DOT_MAX_R = 14;

interface Hsl {
  h: number;
  s: number;
  l: number;
}

interface PvalRamp {
  start: Hsl;
  end: Hsl;
}

/** An unresolved ramp inherits the color of the text around the plot. */
const UNRESOLVED_INK = "currentColor";

const TRIPLE = /^(-?[\d.]+)\s+(-?[\d.]+)%\s+(-?[\d.]+)%$/;

function readTriple(style: CSSStyleDeclaration, variable: string): Hsl | null {
  const match = TRIPLE.exec(style.getPropertyValue(variable).trim());
  if (match === null) return null;
  return { h: Number(match[1]), s: Number(match[2]), l: Number(match[3]) };
}

function rootStyle(): CSSStyleDeclaration | null {
  return typeof document === "undefined"
    ? null
    : getComputedStyle(document.documentElement);
}

function readPvalRamp(): PvalRamp | null {
  const style = rootStyle();
  if (style === null) return null;
  const start = readTriple(style, "--chart-1");
  const end = readTriple(style, "--chart-4");
  return start === null || end === null ? null : { start, end };
}

function round(value: number): number {
  return Number(value.toFixed(2));
}

function paint(color: Hsl): string {
  return hslFromTriple(hslTriple(color.h, color.s, color.l));
}

function mix(ramp: PvalRamp, t: number): string {
  return paint({
    h: round(ramp.start.h + (ramp.end.h - ramp.start.h) * t),
    s: round(ramp.start.s + (ramp.end.s - ramp.start.s) * t),
    l: round(ramp.start.l + (ramp.end.l - ramp.start.l) * t),
  });
}

/** Map -log10(pValue) onto the chart-1 to chart-4 ramp for significance. */
export function pvalColor(pValue: number | null): string {
  if (pValue === null) {
    const style = rootStyle();
    const neutral = style === null ? null : readTriple(style, "--muted-foreground");
    return neutral === null ? UNRESOLVED_INK : paint(neutral);
  }
  const ramp = readPvalRamp();
  if (ramp === null) return UNRESOLVED_INK;
  const negLog = -Math.log10(Math.max(pValue, 1e-20));
  return mix(ramp, Math.min(negLog / 10, 1));
}

/** The legend swatch for `pvalColor`, four stops off the same ramp. */
export function pvalGradient(): string {
  const ramp = readPvalRamp();
  if (ramp === null) return UNRESOLVED_INK;
  const stops = [0, 1 / 3, 2 / 3, 1].map((t) => mix(ramp, t));
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

/** Render a ratio. A null ratio is unbounded, so it has no number. */
export function formatRatio(value: number | null, digits: number): string {
  return value === null ? "Inf" : value.toFixed(digits);
}

/** Render a probability. A null probability is not computable. */
export function formatProbability(value: number | null): string {
  return value === null ? "n/a" : value.toExponential(2);
}

/**
 * Order values ascending. A null ratio is unbounded and a null probability is
 * not computable, so both sort last; reversing the order puts them first.
 */
export function compareNullableAsc(a: number | null, b: number | null): number {
  if (a === null) return b === null ? 0 : 1;
  if (b === null) return -1;
  return a - b;
}

export function fmtCount(n: number): string {
  return n.toLocaleString();
}

/** Truncate a label for chart display. */
export function truncateLabel(label: string, max = 35): string {
  return label.length > max ? label.slice(0, max - 3) + "..." : label;
}

/** Filter terms by p-value threshold. A term with no p-value is not significant. */
export function filterByPThreshold(
  terms: EnrichmentTerm[],
  threshold: number,
): EnrichmentTerm[] {
  return terms.filter((t) => t.pValue !== null && t.pValue <= threshold);
}
