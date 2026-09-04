"use client";

import type { ContrastSummary } from "@pathfinder/shared/generated/types/ContrastSummary";

/**
 * Which way each differential criterion points.
 *
 * WDK computes fold change as comparator-vs-reference, so swapping the two
 * still returns a full, plausible gene set of the opposite biology. That is
 * the one failure mode with nothing to notice: no error, no zero count. Stating
 * the direction in plain words is what makes it catchable.
 */
export function LedgerContrasts({ contrasts }: { contrasts: ContrastSummary[] }) {
  if (contrasts.length === 0) return null;

  return (
    <div className="mt-2 space-y-1">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        Contrast
      </div>
      {contrasts.map((c) => {
        const incomplete =
          c.comparator == null ||
          c.comparator === "" ||
          c.reference == null ||
          c.reference === "";
        return (
          <div key={c.criterionId} className="text-[11px] leading-snug">
            <span className="font-mono text-muted-foreground">{c.criterionId}</span>
            <span className="mx-1 text-muted-foreground">·</span>
            <span className={incomplete ? "text-warning" : "text-foreground"}>
              {c.summary}
            </span>
            {incomplete && (
              <span className="ml-1 text-[10px] text-warning">(incomplete)</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
