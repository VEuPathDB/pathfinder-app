import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { CustomEnrichmentResult } from "@pathfinder/shared/generated/types/CustomEnrichmentResult";
import { runCustomEnrichment } from "@/features/workbench/analysis/api/compute";
import { formatRatio } from "./enrichment-utils";

interface CustomEnrichmentSectionProps {
  experimentId: string;
}

export function CustomEnrichmentSection({
  experimentId,
}: CustomEnrichmentSectionProps) {
  const [geneSetName, setGeneSetName] = useState("");
  const [geneIdsText, setGeneIdsText] = useState("");
  const [results, setResults] = useState<CustomEnrichmentResult[]>([]);

  const enrichMutation = useMutation({
    mutationFn: async (args: { name: string; ids: string[] }) => {
      return runCustomEnrichment(experimentId, args.name, args.ids);
    },
    onSuccess: (result) => {
      setResults((prev) => [result, ...prev]);
      setGeneSetName("");
      setGeneIdsText("");
    },
  });

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Test if results are enriched for your own gene sets using Fisher&apos;s exact
        test.
      </p>

      <div className="space-y-3">
        <Input
          type="text"
          value={geneSetName}
          onChange={(e) => setGeneSetName(e.target.value)}
          placeholder="Gene set name (e.g. ISG response genes)"
          className="h-8 bg-background text-xs"
        />
        <textarea
          value={geneIdsText}
          onChange={(e) => setGeneIdsText(e.target.value)}
          placeholder="Paste gene IDs (one per line, comma, or tab separated)"
          rows={3}
          className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <Button
          size="sm"
          onClick={() => {
            const ids = geneIdsText
              .split(/[\n,\t]+/)
              .map((s) => s.trim())
              .filter(Boolean);
            if (ids.length > 0 && geneSetName.trim()) {
              enrichMutation.mutate({ name: geneSetName.trim(), ids });
            }
          }}
          disabled={
            enrichMutation.isPending || !geneSetName.trim() || !geneIdsText.trim()
          }
          loading={enrichMutation.isPending}
        >
          <Play className="h-3.5 w-3.5" />
          Run Fisher&apos;s Exact Test
        </Button>
      </div>

      {enrichMutation.error != null && (
        <p className="text-xs text-destructive">{enrichMutation.error.message}</p>
      )}

      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((r, i) => (
            <Card key={i} className="p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-foreground">
                  {r.geneSetName}
                </span>
                <Badge
                  variant={r.pValue < 0.05 ? "default" : "secondary"}
                  className="font-mono text-xs"
                >
                  p ={" "}
                  {r.pValue < 0.001 ? r.pValue.toExponential(2) : r.pValue.toFixed(4)}
                </Badge>
              </div>
              <div className="mt-1.5 flex gap-4 text-xs text-muted-foreground">
                <span>
                  Overlap: {r.overlapCount} / {r.tpCount} TP genes
                </span>
                <span>Fold: {r.foldEnrichment.toFixed(2)}x</span>
                <span>Odds Ratio: {formatRatio(r.oddsRatio, 2)}</span>
                <span>
                  Gene set size: {r.geneSetSize} ({r.geneSetInBackground} in background)
                </span>
              </div>
              {r.overlapGenes.length > 0 && (
                <div className="mt-1.5 truncate text-xs font-mono text-muted-foreground">
                  {r.overlapGenes.slice(0, 20).join(", ")}
                  {r.overlapGenes.length > 20 && ` +${r.overlapGenes.length - 20} more`}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
