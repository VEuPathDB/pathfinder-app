import type { AuditRunSummary } from "@pathfinder/shared/generated/types/AuditRunSummary";
import type { RateBounds } from "@pathfinder/shared/generated/types/RateBounds";
import type { Unresolved } from "@pathfinder/shared/generated/types/Unresolved";
import type { UnresolvedWords } from "@pathfinder/shared/generated/types/UnresolvedWords";

const DAY = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

const UNRESOLVED_ORDER: readonly (keyof UnresolvedWords)[] = [
  "screened",
  "unsampled",
  "trying",
  "failed",
  "declined",
  "unreached",
  "unread",
];

function roundHalfEven(value: number): number {
  const rounded = Math.round(value);
  return value % 1 === 0.5 && rounded % 2 === 1 ? rounded - 1 : rounded;
}

export function percent(share: number): string {
  return `${String(roundHalfEven(share * 100))}%`;
}

export function shareText(bounds: RateBounds): string {
  return `${String(bounds.confirmed)} of ${String(bounds.checked)}`;
}

export function rateText(bounds: RateBounds): string {
  return `${percent(bounds.rate)} (${percent(bounds.low)} to ${percent(bounds.high)})`;
}

export function rangeText(bounds: RateBounds): string {
  return `${percent(bounds.floor)} to ${percent(bounds.ceiling)}`;
}

export function plural(count: number, word: string, many = `${word}s`): string {
  return `${count.toLocaleString("en-US")} ${count === 1 ? word : many}`;
}

export function joinWords(items: readonly string[]): string {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1] ?? ""}`;
}

export function dayText(iso: string): string {
  return DAY.format(new Date(iso));
}

export function impactText(impact: number | null): string {
  return impact === null ? "Not weighed" : String(impact);
}

export function scopeText(run: Pick<AuditRunSummary, "genomes" | "targets">): string {
  return joinWords([
    ...run.genomes,
    ...(run.targets > 0 ? [plural(run.targets, "gene target")] : []),
  ]);
}

export function unresolvedText(unresolved: Unresolved, words: UnresolvedWords): string {
  if (unresolved.total === 0) return "0";
  const parts = UNRESOLVED_ORDER.flatMap((key) => {
    const count = unresolved[key] ?? 0;
    return count > 0 ? [`${String(count)} ${words[key]}`] : [];
  });
  return `${String(unresolved.total)} (${parts.join(", ")})`;
}
