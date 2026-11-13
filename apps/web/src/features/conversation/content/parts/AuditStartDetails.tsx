import type { ReactElement } from "react";
import type { AuditStartCard } from "@strategist/shared/generated/types/AuditStartCard";

const NUMBER = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

function duration(hours: number): string {
  if (hours >= 1) return `${NUMBER.format(hours)} hours`;
  return `${String(Math.max(1, Math.round(hours * 60)))} minutes`;
}

function lines(card: AuditStartCard): string[] {
  return [
    `Genomes: ${card.genomes.join(", ")}`,
    ...(card.leftOut.length > 0 ? [`Left out: ${card.leftOut.join(", ")}`] : []),
    ...(card.comparison.length > 0
      ? [`Compared with ${String(card.comparison.length)} genomes`]
      : []),
    ...(card.referenceGenome === null ? [] : [`Reference: ${card.referenceGenome}`]),
    `Checks: ${card.checkTitles.join(", ")}`,
    ...(card.targets > 0 ? [`${String(card.targets)} gene targets`] : []),
    ...card.refusedTargets.map(
      (refused) => `Not checked: ${refused.title}, because ${refused.reason}`,
    ),
    `About ${NUMBER.format(card.wdkRequests)} site requests and ${NUMBER.format(card.storeReads)} genome-store reads`,
    `About ${duration(card.hours)}, at most ${duration(card.hoursAtMost)}`,
    `Up to ${NUMBER.format(card.modelReviews)} model reviews`,
  ];
}

export function AuditStartDetails({ card }: { card: AuditStartCard }): ReactElement {
  return (
    <ul className="space-y-0.5 text-xs">
      {lines(card).map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}
