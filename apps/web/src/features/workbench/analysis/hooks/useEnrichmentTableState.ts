import { useState } from "react";
import type { EnrichmentTerm } from "@pathfinder/shared";
import type { SortDir } from "../constants";
import { compareNullableAsc, type SortKey } from "../components/enrichment-utils";

/** Ascending order for one column. Reversing it flips a missing value's place. */
function compareAsc(a: EnrichmentTerm, b: EnrichmentTerm, key: SortKey): number {
  if (key === "termName") return a.termName.localeCompare(b.termName);
  if (key === "geneCount") return a.geneCount - b.geneCount;
  return compareNullableAsc(a[key], b[key]);
}

interface EnrichmentTableState {
  sorted: EnrichmentTerm[];
  sortKey: SortKey;
  sortDir: SortDir;
  expandedIds: Set<string>;
  toggleSort: (key: SortKey) => void;
  toggleExpand: (termId: string) => void;
}

export function useEnrichmentTableState(terms: EnrichmentTerm[]): EnrichmentTableState {
  const [sortKey, setSortKey] = useState<SortKey>("pValue");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const sorted = (() => {
    const copy = [...terms];
    copy.sort((a, b) => {
      const ascending = compareAsc(a, b, sortKey);
      return sortDir === "asc" ? ascending : -ascending;
    });
    return copy;
  })();

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(
        key === "termName" || key === "pValue" || key === "fdr" ? "asc" : "desc",
      );
    }
  };

  const toggleExpand = (termId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(termId)) {
        next.delete(termId);
      } else {
        next.add(termId);
      }
      return next;
    });
  };

  return { sorted, sortKey, sortDir, expandedIds, toggleSort, toggleExpand };
}
