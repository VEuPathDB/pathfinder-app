import type { CrossValidationResult } from "@pathfinder/shared";
import { Layers } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Section } from "./Section";
import { pct } from "../utils/formatters";

interface CrossValidationSectionProps {
  cv: CrossValidationResult;
}

const OVERFITTING_STYLES: Record<string, { label: string; className: string }> = {
  low: { label: "Low", className: "text-success" },
  moderate: { label: "Moderate", className: "text-warning" },
  high: { label: "High", className: "text-destructive" },
};

const SUMMARY_METRICS: {
  key: keyof CrossValidationResult["meanMetrics"];
  label: string;
}[] = [
  { key: "sensitivity", label: "Sensitivity" },
  { key: "specificity", label: "Specificity" },
  { key: "f1Score", label: "F1 Score" },
  { key: "precision", label: "Precision" },
  { key: "mcc", label: "MCC" },
];

export function CrossValidationSection({ cv }: CrossValidationSectionProps) {
  const overfitting = OVERFITTING_STYLES[cv.overfittingLevel ?? "low"] ?? {
    label: "Low",
    className: "text-success",
  };

  return (
    <Section title="K-Fold Cross-Validation">
      <div className="space-y-4">
        {/* Header card: fold count + overfitting */}
        <Card className="flex items-center gap-3 px-5 py-3">
          <Layers className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">
            {cv.k}-fold cross-validation
          </span>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Overfitting risk:</span>
            <Badge variant="secondary" className={`text-xs ${overfitting.className}`}>
              {overfitting.label}
            </Badge>
            <span className="font-mono text-xs text-muted-foreground">
              ({((cv.overfittingScore ?? 0) * 100).toFixed(0)}%)
            </span>
          </div>
        </Card>

        {/* Per-fold table */}
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                  Fold
                </th>
                <th className="px-4 py-2 text-right font-medium text-muted-foreground">
                  Sensitivity
                </th>
                <th className="px-4 py-2 text-right font-medium text-muted-foreground">
                  Specificity
                </th>
                <th className="px-4 py-2 text-right font-medium text-muted-foreground">
                  F1
                </th>
              </tr>
            </thead>
            <tbody>
              {cv.folds.map((fold) => (
                <tr
                  key={fold.foldIndex}
                  className="border-b border-border last:border-0"
                >
                  <td className="px-4 py-2 font-mono font-medium">
                    {fold.foldIndex + 1}
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {pct(fold.metrics.sensitivity)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {pct(fold.metrics.specificity)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {pct(fold.metrics.f1Score)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Summary: mean +/- std */}
        <div>
          <h4 className="mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Summary (mean +/- std)
          </h4>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {SUMMARY_METRICS.map(({ key, label }) => {
              const mean = cv.meanMetrics[key];
              const std = cv.stdMetrics?.[key] ?? null;
              if (typeof mean !== "number") return null;
              return (
                <Card key={key} className="px-4 py-3 text-center">
                  <div className="text-xs text-muted-foreground">{label}</div>
                  <div className="mt-1 font-mono text-sm font-semibold tabular-nums text-foreground">
                    {pct(mean)}
                  </div>
                  {typeof std === "number" && (
                    <div className="font-mono text-[11px] tabular-nums text-muted-foreground">
                      +/- {pct(std)}
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      </div>
    </Section>
  );
}
