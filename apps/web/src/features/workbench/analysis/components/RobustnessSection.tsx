import type { BootstrapResult, ConfidenceInterval } from "@pathfinder/shared";
import { Badge } from "@/components/ui/badge";
import { Section } from "./Section";
import { pct } from "../utils/formatters";

interface RobustnessSectionProps {
  robustness: BootstrapResult;
}

const METRIC_DISPLAY: Record<string, string> = {
  sensitivity: "Sensitivity",
  specificity: "Specificity",
  precision: "Precision",
  f1_score: "F1 Score",
};

function CIRow({ label, ci }: { label: string; ci: ConfidenceInterval }) {
  const widthIsNarrow = (ci.upper ?? 0) - (ci.lower ?? 0) < 0.15;
  return (
    <tr className="border-b border-border last:border-0">
      <td className="px-4 py-2 text-sm text-foreground">{label}</td>
      <td className="px-4 py-2 text-right font-mono text-sm tabular-nums">
        {pct(ci.mean)}
      </td>
      <td className="px-4 py-2 text-right font-mono text-xs tabular-nums text-muted-foreground">
        [{pct(ci.lower)}, {pct(ci.upper)}]
      </td>
      <td className="px-4 py-2 text-right text-xs">
        <Badge
          variant="secondary"
          className={`text-[10px] ${widthIsNarrow ? "text-success" : "text-warning"}`}
        >
          {widthIsNarrow ? "Tight" : "Wide"}
        </Badge>
      </td>
    </tr>
  );
}

export function RobustnessSection({ robustness }: RobustnessSectionProps) {
  const ciEntries = Object.entries(robustness.metricCis ?? {}).filter(
    ([k]) => k in METRIC_DISPLAY,
  );
  if (ciEntries.length === 0) return null;

  return (
    <Section title="Robustness & Uncertainty">
      <div className="space-y-4">
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40">
                <th className="px-4 py-2 text-left font-medium text-muted-foreground">
                  Metric
                </th>
                <th className="px-4 py-2 text-right font-medium text-muted-foreground">
                  Mean
                </th>
                <th className="px-4 py-2 text-right font-medium text-muted-foreground">
                  95% CI
                </th>
                <th className="px-4 py-2 text-right font-medium text-muted-foreground">
                  Width
                </th>
              </tr>
            </thead>
            <tbody>
              {ciEntries.map(([key, ci]) => (
                <CIRow key={key} label={METRIC_DISPLAY[key] ?? key} ci={ci} />
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground">
          {robustness.nIterations} bootstrap iterations
        </p>
      </div>
    </Section>
  );
}
