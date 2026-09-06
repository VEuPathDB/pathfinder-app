"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Dna, Play, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EnrichmentSection } from "@/features/workbench/analysis";
import { toUserMessage } from "@/lib/api/errors";
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { useWorkbenchStore } from "@/state/useWorkbenchStore";
import { useSessionStore } from "@/state/useSessionStore";
import { useGeneSetsQuery } from "@/features/workbench/hooks/useGeneSetsQuery";
import { useInvalidateGeneSets } from "@/features/workbench/hooks/useInvalidateGeneSets";
import { enrichGeneSet } from "../../api/geneSets";

// ---------------------------------------------------------------------------
// Enrichment type chips
// ---------------------------------------------------------------------------

const ENRICHMENT_TYPES = [
  { key: "go_process", label: "GO:BP" },
  { key: "go_function", label: "GO:MF" },
  { key: "go_component", label: "GO:CC" },
  { key: "pathway", label: "Pathway" },
  { key: "word", label: "Word" },
] as const;

type EnrichmentTypeKey = (typeof ENRICHMENT_TYPES)[number]["key"];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function EnrichmentPanel() {
  const selectedSite = useSessionStore((s) => s.selectedSite);
  const { data: geneSets = [] } = useGeneSetsQuery(selectedSite);
  const activeSetId = useWorkbenchStore((s) => s.activeSetId);
  const activeSet = geneSets.find((gs) => gs.id === activeSetId);
  const invalidateGeneSets = useInvalidateGeneSets();

  const [selectedTypes, setSelectedTypes] = useState<Set<EnrichmentTypeKey>>(
    new Set(ENRICHMENT_TYPES.map((t) => t.key)),
  );

  // The API saves each run on the gene set, so the panel reads the saved
  // analyses and a set the researcher comes back to still shows its results.
  const results = activeSet?.enrichmentResults ?? [];

  const run = useMutation({
    mutationFn: async (setId: string) => enrichGeneSet(setId, [...selectedTypes]),
    onSuccess: async () => {
      await invalidateGeneSets();
    },
  });

  const toggleType = (key: EnrichmentTypeKey) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const loading = run.isPending;
  const error = run.error === null ? null : toUserMessage(run.error);
  const ranAndFoundNothing = run.isSuccess && results.length === 0;

  return (
    <AnalysisPanelContainer
      panelId="enrichment"
      title="Enrichment Analysis"
      subtitle="GO terms, pathways, and word enrichment"
      icon={<Dna className="h-4 w-4" />}
    >
      <div className="space-y-4">
        {/* Type selector chips */}
        <div className="flex flex-wrap items-center gap-2">
          {ENRICHMENT_TYPES.map(({ key, label }) => {
            const active = selectedTypes.has(key);
            return (
              <button
                key={key}
                type="button"
                onClick={() => toggleType(key)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  active
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border bg-card text-muted-foreground hover:border-primary/40"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

        {/* Run button */}
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            onClick={() => {
              if (activeSet == null || selectedTypes.size === 0) return;
              run.mutate(activeSet.id);
            }}
            disabled={loading || !activeSet || selectedTypes.size === 0}
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {loading ? "Running..." : "Run Enrichment"}
          </Button>
          {loading && (
            <span className="text-xs text-muted-foreground">
              Analyzing {selectedTypes.size} enrichment type
              {selectedTypes.size !== 1 ? "s" : ""}...
            </span>
          )}
        </div>

        {error !== null && <p className="text-xs text-destructive">{error}</p>}

        {results.length > 0 && <EnrichmentSection results={results} />}

        {ranAndFoundNothing && (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No enrichment results returned. Try different enrichment types.
          </p>
        )}
      </div>
    </AnalysisPanelContainer>
  );
}
