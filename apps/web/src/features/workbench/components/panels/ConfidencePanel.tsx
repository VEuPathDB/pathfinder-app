"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, ShieldCheck } from "lucide-react";
import type {
  Experiment,
  EnrichmentResult,
  GeneConfidenceRequest,
} from "@pathfinder/shared";
import { geneConfidenceScoreResponseSchema } from "@pathfinder/shared/generated/zod/geneConfidenceScoreResponseSchema";
import { z } from "zod";

import { requestJson } from "@/lib/api/http";

const GeneConfidenceScoreListSchema = z.array(geneConfidenceScoreResponseSchema);
import { AnalysisPanelContainer } from "../AnalysisPanelContainer";
import { useActiveSetExperiment } from "@/features/workbench/hooks/useActiveSetExperiment";

// ---------------------------------------------------------------------------
// Enrichment data extraction (prepares input for the backend)
// ---------------------------------------------------------------------------

function extractEnrichmentCounts(enrichmentResults: EnrichmentResult[]): {
  enrichmentGeneCounts: Record<string, number>;
  maxEnrichmentTerms: number;
} {
  const counts: Record<string, number> = {};
  let maxTerms = 0;
  for (const result of enrichmentResults) {
    for (const term of result.terms) {
      if (term.fdr !== null && term.fdr <= 0.05) {
        maxTerms++;
        for (const geneId of term.genes ?? []) {
          counts[geneId] = (counts[geneId] ?? 0) + 1;
        }
      }
    }
  }
  return { enrichmentGeneCounts: counts, maxEnrichmentTerms: maxTerms };
}

// ---------------------------------------------------------------------------
// Score color helper
// ---------------------------------------------------------------------------

function scoreColor(value: number): string {
  if (value > 0.15) return "text-success";
  if (value < -0.15) return "text-destructive";
  return "text-muted-foreground";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function hasClassifiedGenes(exp: Experiment): boolean {
  return (
    (exp.truePositiveGenes?.length ?? 0) > 0 ||
    (exp.falsePositiveGenes?.length ?? 0) > 0 ||
    (exp.falseNegativeGenes?.length ?? 0) > 0 ||
    (exp.trueNegativeGenes?.length ?? 0) > 0
  );
}

export function ConfidencePanel() {
  const experiment = useActiveSetExperiment();

  const isRelevant = experiment != null && hasClassifiedGenes(experiment) === true;

  const requestBody = ((): GeneConfidenceRequest | null => {
    if (!experiment || !hasClassifiedGenes(experiment)) return null;
    const { enrichmentGeneCounts, maxEnrichmentTerms } = extractEnrichmentCounts(
      experiment.enrichmentResults ?? [],
    );
    return {
      tpIds: (experiment.truePositiveGenes ?? []).map((g) => g.id),
      fpIds: (experiment.falsePositiveGenes ?? []).map((g) => g.id),
      fnIds: (experiment.falseNegativeGenes ?? []).map((g) => g.id),
      tnIds: (experiment.trueNegativeGenes ?? []).map((g) => g.id),
      ...(Object.keys(enrichmentGeneCounts).length > 0 ? { enrichmentGeneCounts } : {}),
      // The field is the enrichment divisor, so it needs at least one term.
      ...(maxEnrichmentTerms > 0 ? { maxEnrichmentTerms } : {}),
    };
  })();

  const {
    data: scores = [],
    isPending: loading,
    error: queryError,
  } = useQuery({
    queryKey: ["gene-confidence", experiment?.id] as const,
    queryFn: () =>
      requestJson(GeneConfidenceScoreListSchema, "/api/v1/gene-sets/confidence", {
        method: "POST",
        body: requestBody!,
      }),
    enabled: isRelevant && requestBody != null,
    retry: false,
  });
  const error = queryError instanceof Error ? queryError.message : null;

  return (
    <AnalysisPanelContainer
      panelId="confidence"
      title="Gene Confidence"
      subtitle="Per-gene composite confidence ranking"
      icon={<ShieldCheck className="h-4 w-4" />}
      disabled={!isRelevant}
      disabledReason="Requires an experiment with classified genes"
    >
      {loading && (
        <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Computing scores...
        </div>
      )}

      {error != null && <p className="text-xs text-destructive">{error}</p>}

      {!loading && error == null && scores.length > 0 && (
        <div className="max-h-96 overflow-auto">
          <table role="table" data-testid="confidence-table" className="w-full text-xs">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="pb-1.5 pr-3 font-medium">Gene ID</th>
                <th className="pb-1.5 pr-3 font-medium">Composite</th>
                <th className="pb-1.5 pr-3 font-medium">Classification</th>
                <th className="pb-1.5 pr-3 font-medium">Ensemble</th>
                <th className="pb-1.5 font-medium">Enrichment</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s) => (
                <tr
                  key={s.geneId}
                  data-testid="confidence-row"
                  data-gene-id={s.geneId}
                  className="border-b border-border/50"
                >
                  <td data-cell="gene-id" className="py-1 pr-3 font-mono">
                    {s.geneId}
                  </td>
                  <td
                    data-cell="composite"
                    className={`py-1 pr-3 ${scoreColor(s.compositeScore)}`}
                  >
                    {s.compositeScore.toFixed(3)}
                  </td>
                  <td className={`py-1 pr-3 ${scoreColor(s.classificationScore)}`}>
                    {s.classificationScore.toFixed(1)}
                  </td>
                  <td className={`py-1 pr-3 ${scoreColor(s.ensembleScore)}`}>
                    {s.ensembleScore.toFixed(2)}
                  </td>
                  <td className={`py-1 ${scoreColor(s.enrichmentScore)}`}>
                    {s.enrichmentScore.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AnalysisPanelContainer>
  );
}
