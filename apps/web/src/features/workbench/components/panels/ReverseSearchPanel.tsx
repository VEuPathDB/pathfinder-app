"use client";

import { useState } from "react";
import { Search, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { requestJson } from "@/lib/api/http";
import { reverseSearchResultItemSchema } from "@pathfinder/shared/generated/zod/reverseSearchResultItemSchema";
import type { ReverseSearchRequest } from "@pathfinder/shared/generated/types/ReverseSearchRequest";
import type { ReverseSearchResultItem } from "@pathfinder/shared/generated/types/ReverseSearchResultItem";
import { z } from "zod";
import { useSessionStore } from "@/state/useSessionStore";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { GeneChipInput } from "../GeneChipInput";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";

const ReverseSearchResultListSchema = z.array(reverseSearchResultItemSchema);

type ReverseSearchResult = ReverseSearchResultItem;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ReverseSearchPanel() {
  const siteId = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(siteId);
  const hasGeneSets = geneSets.length > 0;

  const [positiveInput, setPositiveInput] = useState<string[]>([]);
  const [negativeInput, setNegativeInput] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<ReverseSearchResult[]>([]);

  const disabled = !siteId;

  const handleSearch = async () => {
    if (positiveInput.length === 0) {
      setError("Enter at least one positive gene ID.");
      return;
    }

    setLoading(true);
    setError(null);
    setResults([]);

    const body: ReverseSearchRequest = {
      positiveGeneIds: positiveInput,
      negativeGeneIds: negativeInput.length > 0 ? negativeInput : null,
      siteId,
    };

    try {
      const data = await requestJson(
        ReverseSearchResultListSchema,
        "/api/v1/gene-sets/reverse-search",
        { method: "POST", body },
      );
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnalysisPanelContainer
      panelId="reverse-search"
      title="Reverse Search"
      subtitle="Find which gene sets best recover your target genes"
      icon={<Search className="h-4 w-4" />}
      disabled={disabled}
      disabledReason="Select a site first"
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <GeneChipInput
            siteId={siteId}
            value={positiveInput}
            onChange={setPositiveInput}
            label="Positive Gene IDs"
            tint="positive"
            required
          />
          <GeneChipInput
            siteId={siteId}
            value={negativeInput}
            onChange={setNegativeInput}
            label="Negative Gene IDs"
            tint="negative"
          />
        </div>

        <Button
          size="sm"
          onClick={() => {
            void handleSearch();
          }}
          disabled={loading || !hasGeneSets}
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Search className="h-3.5 w-3.5" />
          )}
          {loading ? "Searching..." : "Search"}
        </Button>

        {!hasGeneSets && (
          <p className="text-xs text-muted-foreground">
            Add gene sets to the workbench first.
          </p>
        )}

        {error != null && error !== "" && (
          <p className="text-xs text-destructive">{error}</p>
        )}

        {results.length > 0 && (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium">#</th>
                  <th className="px-3 py-2 text-left font-medium">Gene Set</th>
                  <th className="px-3 py-2 text-left font-medium">Search</th>
                  <th className="px-3 py-2 text-right font-medium">Recall</th>
                  <th className="px-3 py-2 text-right font-medium">Precision</th>
                  <th className="px-3 py-2 text-right font-medium">F1</th>
                  <th className="px-3 py-2 text-right font-medium">Overlap</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr
                    key={r.geneSetId}
                    className="border-b last:border-0 hover:bg-muted/30"
                  >
                    <td className="px-3 py-2 text-muted-foreground">{i + 1}</td>
                    <td className="px-3 py-2 font-medium">{r.name}</td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {r.searchName ?? "-"}
                    </td>
                    <td className="px-3 py-2 text-right">{pct(r.recall)}</td>
                    <td className="px-3 py-2 text-right">{pct(r.precision)}</td>
                    <td className="px-3 py-2 text-right">{pct(r.f1)}</td>
                    <td className="px-3 py-2 text-right">
                      {r.overlapCount}/{r.estimatedSize}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AnalysisPanelContainer>
  );
}
