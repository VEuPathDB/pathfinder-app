import { Fragment } from "react";
import type { EnrichmentTerm } from "@pathfinder/shared";
import { ArrowUpDown, ChevronRight } from "lucide-react";
import { useEnrichmentTableState } from "../hooks/useEnrichmentTableState";
import {
  fmtCount,
  formatProbability,
  formatRatio,
  type SortKey,
} from "./enrichment-utils";

// ---------------------------------------------------------------------------
// Column definitions
// ---------------------------------------------------------------------------

const COLUMNS: { key: SortKey; label: string; align?: string }[] = [
  { key: "termName", label: "Term" },
  { key: "geneCount", label: "Genes", align: "text-right" },
  { key: "foldEnrichment", label: "Fold", align: "text-right" },
  { key: "pValue", label: "p-value", align: "text-right" },
  { key: "fdr", label: "FDR", align: "text-right" },
];

// ---------------------------------------------------------------------------
// Expanded row details (odds ratio, bonferroni, gene list)
// ---------------------------------------------------------------------------

function ExpandedTermDetails({ term }: { term: EnrichmentTerm }) {
  return (
    <div className="space-y-2 text-xs">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
        <span>
          Background:{" "}
          <span className="font-mono text-foreground">
            {fmtCount(term.backgroundCount)}
          </span>
        </span>
        <span>
          Odds Ratio:{" "}
          <span className="font-mono text-foreground">
            {formatRatio(term.oddsRatio, 3)}
          </span>
        </span>
        <span>
          Bonferroni:{" "}
          <span className="font-mono text-foreground">
            {formatProbability(term.bonferroni)}
          </span>
        </span>
      </div>

      {term.genes && term.genes.length > 0 && (
        <div>
          <span className="text-muted-foreground">Genes ({term.genes.length}):</span>
          <div className="mt-1 flex flex-wrap gap-1">
            {term.genes.map((gene) => (
              <span
                key={gene}
                className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-foreground"
              >
                {gene}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main table component
// ---------------------------------------------------------------------------

interface EnrichmentTableProps {
  terms: EnrichmentTerm[];
}

export function EnrichmentTable({ terms }: EnrichmentTableProps) {
  const { sorted, expandedIds, toggleSort, toggleExpand } =
    useEnrichmentTableState(terms);

  if (terms.length === 0) {
    return (
      <div className="px-5 py-8 text-center text-xs text-muted-foreground">
        No enriched terms at this threshold.
      </div>
    );
  }

  return (
    <div
      className="max-h-96 overflow-y-auto"
      tabIndex={0}
      role="region"
      aria-label="Enrichment results table"
    >
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-card">
          <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
            <th className="w-6 px-2 py-2.5" />
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`cursor-pointer select-none px-4 py-2.5 font-medium transition-colors duration-150 ${col.align ?? ""}`}
                onClick={() => toggleSort(col.key)}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  <ArrowUpDown className="h-2.5 w-2.5" />
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {sorted.map((t, idx) => {
            const rowKey = t.termId || `term-${idx}`;
            const expanded = expandedIds.has(rowKey);
            return (
              <Fragment key={rowKey}>
                <tr
                  className="cursor-pointer transition hover:bg-accent"
                  onClick={() => toggleExpand(rowKey)}
                >
                  <td className="px-2 py-2 text-muted-foreground">
                    <ChevronRight
                      className={`h-3 w-3 transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
                    />
                  </td>
                  <td className="max-w-xs truncate px-4 py-2 text-foreground">
                    {t.termId && (
                      <span className="mr-1.5 font-mono text-xs text-muted-foreground">
                        {t.termId}
                      </span>
                    )}
                    {t.termName || t.termId || "\u2014"}
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-muted-foreground">
                    {t.geneCount}
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-muted-foreground">
                    {formatRatio(t.foldEnrichment, 2)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-muted-foreground">
                    {formatProbability(t.pValue)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums text-muted-foreground">
                    {formatProbability(t.fdr)}
                  </td>
                </tr>
                {expanded && (
                  <tr>
                    <td colSpan={6} className="bg-muted/20 px-6 py-3">
                      <ExpandedTermDetails term={t} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
