"use client";

import { useEdaStore } from "@/state/eda";

import { CellShell } from "./CellShell";

const MUTED = "text-[11px] text-muted-foreground";

/** The subset the analysis holds, as text. The site's notebook edits it. */
export function SubsetSummary() {
  const analysis = useEdaStore((s) => s.analysis);
  if (analysis === null) return null;
  const hidden = analysis.numFilters - analysis.filterSummaries.length;

  return (
    <CellShell title="Subset" subtitle={null} testId="eda-subset-summary">
      {analysis.filterSummaries.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {analysis.filterSummaries.map((summary, index) => (
            <li
              key={index}
              data-testid={`eda-filter-chip-${String(index)}`}
              className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px]"
            >
              {summary}
            </li>
          ))}
        </ul>
      ) : (
        <p data-testid="eda-subset-no-filters" className={MUTED}>
          No filters: the subset is the whole study.
        </p>
      )}
      {hidden > 0 ? (
        <p data-testid="eda-subset-filter-overflow" className={`mt-1 ${MUTED}`}>
          {`${hidden.toLocaleString()} more ${hidden === 1 ? "filter" : "filters"}`}
        </p>
      ) : null}
      <ul className="mt-3 space-y-0.5 text-xs">
        {analysis.entityCounts.map((row) => (
          <li key={row.entityId} data-testid={`eda-entity-count-${row.entityId}`}>
            {`${row.count.toLocaleString()} of ${row.unfilteredCount.toLocaleString()} ${row.entityDisplayName}`}
          </li>
        ))}
      </ul>
    </CellShell>
  );
}
