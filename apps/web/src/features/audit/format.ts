import type { AuditRunSummary } from "@strategist/shared/generated/types/AuditRunSummary";
import type { FindingDetail } from "@strategist/shared/generated/types/FindingDetail";
import type { GenomeView } from "@strategist/shared/generated/types/GenomeView";
import type { RateBounds } from "@strategist/shared/generated/types/RateBounds";
import type { Unresolved } from "@strategist/shared/generated/types/Unresolved";
import type { UnresolvedWords } from "@strategist/shared/generated/types/UnresolvedWords";

const DAY = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});

function roundHalfEven(value: number): number {
  const rounded = Math.round(value);
  return value % 1 === 0.5 && rounded % 2 === 1 ? rounded - 1 : rounded;
}

export function percent(share: number): string {
  const rounded = roundHalfEven(share * 100);
  if (rounded === 0 && share > 0) return "<1%";
  if (rounded === 100 && share < 1) return ">99%";
  return `${String(rounded)}%`;
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

export function findingRequestsText({
  finding,
  evidence,
}: Pick<FindingDetail, "finding" | "evidence">): string | null {
  const rows = [finding, ...evidence];
  const total = rows.reduce((sum, row) => sum + row.requests, 0);
  const uncounted = rows.some((row) => row.stopped > 0 || row.status === "trying");
  const settled = rows.some((row) => row.attempts > row.stopped);
  if (total === 0 && (uncounted || !settled)) return null;
  const counted = plural(total, "site request");
  return uncounted ? `At least ${counted}` : counted;
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
  const counts: Record<string, number | undefined> = unresolved;
  const parts = Object.entries(words).flatMap(([key, text]) => {
    const count = counts[key] ?? 0;
    return count > 0 ? [`${String(count)} ${text}`] : [];
  });
  return `${String(unresolved.total)} (${parts.join(", ")})`;
}

export function gapText(genome: GenomeView): string {
  if (genome.priority !== null) return `${String(genome.priority.gap)} points`;
  if (genome.message !== null) return "Not known: see the note";
  return genome.status === "collected" ? "Not served by the site" : "Not read yet";
}
