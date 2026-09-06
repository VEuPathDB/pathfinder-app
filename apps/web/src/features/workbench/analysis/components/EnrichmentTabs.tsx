import type { EnrichmentResult } from "@pathfinder/shared";
import { AlertCircle } from "lucide-react";
import { ENRICHMENT_ANALYSIS_LABELS } from "../constants";
import { filterByPThreshold } from "./enrichment-utils";

interface EnrichmentTabsProps {
  results: EnrichmentResult[];
  activeTab: number;
  pThreshold: number;
  onTabChange: (index: number) => void;
}

export function EnrichmentTabs({
  results,
  activeTab,
  pThreshold,
  onTabChange,
}: EnrichmentTabsProps) {
  return (
    <div className="flex items-center gap-0">
      {results.map((r, i) => {
        const hasError = r.error != null;
        const count = filterByPThreshold(r.terms, pThreshold).length;
        return (
          <button
            key={r.analysisType}
            type="button"
            onClick={() => onTabChange(i)}
            className={`relative flex items-center gap-1 px-3 py-2.5 text-xs font-medium transition ${
              activeTab === i
                ? "text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {hasError && <AlertCircle className="h-3 w-3 shrink-0 text-destructive" />}
            {ENRICHMENT_ANALYSIS_LABELS[r.analysisType]}
            {!hasError && (
              <span className="text-xs text-muted-foreground">{count}</span>
            )}
            {activeTab === i && (
              <span className="absolute bottom-0 left-0 right-0 h-[2px] bg-primary" />
            )}
          </button>
        );
      })}
    </div>
  );
}
