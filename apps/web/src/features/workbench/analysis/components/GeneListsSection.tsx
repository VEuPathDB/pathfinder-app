import { useState } from "react";
import type { Experiment, GeneInfo } from "@pathfinder/shared";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Section } from "./Section";

interface GeneListsSectionProps {
  experiment: Experiment;
}

export function GeneListsSection({ experiment }: GeneListsSectionProps) {
  const lists = [
    { label: "True Positives", genes: experiment.truePositiveGenes ?? [] },
    { label: "False Negatives", genes: experiment.falseNegativeGenes ?? [] },
    { label: "False Positives", genes: experiment.falsePositiveGenes ?? [] },
    { label: "True Negatives", genes: experiment.trueNegativeGenes ?? [] },
  ];

  return (
    <Section title="Gene Lists">
      <Card className="divide-y divide-border">
        {lists.map((list) => (
          <GeneListRow key={list.label} label={list.label} genes={list.genes} />
        ))}
      </Card>
    </Section>
  );
}

function GeneListRow({ label, genes }: { label: string; genes: GeneInfo[] }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 px-5 py-2.5 text-left transition hover:bg-accent"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="text-sm text-foreground">{label}</span>
        <span className="ml-auto font-mono text-xs tabular-nums text-muted-foreground">
          {genes.length}
        </span>
      </button>
      {expanded && genes.length > 0 && (
        <div className="border-t border-border bg-muted/40 px-5 py-3">
          <div className="max-h-40 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="pb-1.5 pr-4 font-medium">ID</th>
                  <th className="pb-1.5 font-medium">Product</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {genes.slice(0, 100).map((g) => (
                  <tr key={g.id}>
                    <td className="py-1 pr-4 font-mono text-foreground">{g.id}</td>
                    <td className="py-1 text-muted-foreground">{g.product ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {genes.length > 100 && (
              <div className="mt-2 text-xs text-muted-foreground">
                Showing 100 of {genes.length} genes
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
