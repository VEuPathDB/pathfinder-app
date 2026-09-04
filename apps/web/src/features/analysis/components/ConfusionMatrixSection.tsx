import type { ConfusionMatrix } from "@pathfinder/shared";
import { Card } from "@/components/ui/card";
import { Section } from "./Section";

interface ConfusionMatrixSectionProps {
  cm: ConfusionMatrix;
}

export function ConfusionMatrixSection({ cm }: ConfusionMatrixSectionProps) {
  const total =
    cm.truePositives + cm.falsePositives + cm.trueNegatives + cm.falseNegatives;

  const pctOf = (v: number) => (total > 0 ? `${((v / total) * 100).toFixed(1)}%` : "");

  return (
    <Section title="Confusion Matrix">
      <Card className="inline-block">
        <table className="text-center text-sm">
          <thead>
            <tr>
              <th className="w-24" />
              <th
                colSpan={2}
                className="border-b border-border px-4 py-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground"
              >
                Predicted
              </th>
            </tr>
            <tr>
              <th className="border-r border-border px-4 py-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                Actual
              </th>
              <th className="w-32 border-r border-b border-border px-4 py-2 text-xs font-medium text-muted-foreground">
                Positive
              </th>
              <th className="w-32 border-b border-border px-4 py-2 text-xs font-medium text-muted-foreground">
                Negative
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="border-r border-b border-border px-4 py-2 text-xs font-medium text-muted-foreground">
                Positive
              </td>
              <td className="border-r border-b border-border bg-accent px-4 py-3">
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {cm.truePositives}
                </div>
                <div className="text-xs text-muted-foreground">
                  {pctOf(cm.truePositives)} TP
                </div>
              </td>
              <td className="border-b border-border px-4 py-3">
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {cm.falseNegatives}
                </div>
                <div className="text-xs text-muted-foreground">
                  {pctOf(cm.falseNegatives)} FN
                </div>
              </td>
            </tr>
            <tr>
              <td className="border-r border-border px-4 py-2 text-xs font-medium text-muted-foreground">
                Negative
              </td>
              <td className="border-r border-border px-4 py-3">
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {cm.falsePositives}
                </div>
                <div className="text-xs text-muted-foreground">
                  {pctOf(cm.falsePositives)} FP
                </div>
              </td>
              <td className="bg-accent px-4 py-3">
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {cm.trueNegatives}
                </div>
                <div className="text-xs text-muted-foreground">
                  {pctOf(cm.trueNegatives)} TN
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </Card>
      <div className="mt-2 text-xs text-muted-foreground">
        n = {total} &middot; {cm.truePositives + cm.falseNegatives} actual positives
        &middot; {cm.trueNegatives + cm.falsePositives} actual negatives
      </div>
    </Section>
  );
}
