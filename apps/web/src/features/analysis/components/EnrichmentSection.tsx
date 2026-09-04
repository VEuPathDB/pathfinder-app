import { useState } from "react";
import type { EnrichmentResult } from "@pathfinder/shared";
import { AlertCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Section } from "./Section";
import { EnrichmentTabs } from "./EnrichmentTabs";
import { PThresholdFilter } from "./PThresholdFilter";
import { EnrichmentDotPlot } from "./EnrichmentDotPlot";
import { EnrichmentTable } from "./EnrichmentTable";
import { filterByPThreshold, fmtCount } from "./enrichment-utils";

interface EnrichmentSectionProps {
  results: EnrichmentResult[];
}

export function EnrichmentSection({ results }: EnrichmentSectionProps) {
  const [activeTab, setActiveTab] = useState(0);
  const [pThreshold, setPThreshold] = useState(0.05);
  const [prevResults, setPrevResults] = useState(results);

  if (results !== prevResults) {
    setPrevResults(results);
    setActiveTab(0);
  }

  const activeResult = results[activeTab];
  const filtered = filterByPThreshold(activeResult?.terms ?? [], pThreshold);

  return (
    <Section title="Enrichment Analysis">
      <Card>
        {/* Tab bar + p-value filter */}
        <div className="flex items-center gap-0 border-b border-border px-4">
          <EnrichmentTabs
            results={results}
            activeTab={activeTab}
            pThreshold={pThreshold}
            onTabChange={setActiveTab}
          />
          <PThresholdFilter value={pThreshold} onChange={setPThreshold} />
        </div>

        {activeResult?.error != null && (
          <div className="flex items-center gap-2 px-5 py-6 text-xs text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>Analysis failed: {activeResult.error}</span>
          </div>
        )}
        {activeResult != null && activeResult.error == null && (
          <>
            <SummaryBar result={activeResult} filteredCount={filtered.length} />
            {filtered.length > 0 && <EnrichmentDotPlot terms={filtered} />}
            <EnrichmentTable terms={filtered} />
          </>
        )}
      </Card>
    </Section>
  );
}

// ---------------------------------------------------------------------------
// Summary statistics bar (small, kept inline)
// ---------------------------------------------------------------------------

function SummaryBar({
  result,
  filteredCount,
}: {
  result: EnrichmentResult;
  filteredCount: number;
}) {
  return (
    <div className="flex items-center gap-4 border-b border-border/50 bg-muted/30 px-4 py-2 text-xs text-muted-foreground">
      <span>
        <span className="font-medium text-foreground">{filteredCount}</span> significant
        term{filteredCount !== 1 ? "s" : ""}
      </span>
      {(result.totalGenesAnalyzed ?? 0) > 0 && (
        <span>{fmtCount(result.totalGenesAnalyzed ?? 0)} genes analyzed</span>
      )}
      {(result.backgroundSize ?? 0) > 0 && (
        <span>background: {fmtCount(result.backgroundSize ?? 0)}</span>
      )}
    </div>
  );
}
