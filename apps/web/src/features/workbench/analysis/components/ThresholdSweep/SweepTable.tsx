import type { ThresholdSweepPoint } from "@/features/workbench/analysis/api/compute";
import { pct } from "../../utils/formatters";

export function SweepTable({
  points,
  parameter,
  formatValue,
}: {
  points: ThresholdSweepPoint[];
  parameter: string;
  formatValue: (v: number | string) => string;
}) {
  return (
    <div className="max-h-52 overflow-y-auto rounded-md border border-border">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-card">
          <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
            <th className="px-3 py-2 font-medium">{parameter}</th>
            <th className="px-3 py-2 font-medium">Sensitivity</th>
            <th className="px-3 py-2 font-medium">Specificity</th>
            <th className="px-3 py-2 font-medium">F1</th>
            <th className="px-3 py-2 font-medium">MCC</th>
            <th className="px-3 py-2 font-medium">Bal. Acc.</th>
            <th className="px-3 py-2 font-medium">Results</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/50">
          {points.map((p) => (
            <tr key={String(p.value)}>
              <td className="px-3 py-1.5 font-mono text-foreground">
                {formatValue(p.value)}
              </td>
              <td className="px-3 py-1.5 font-mono text-muted-foreground">
                {pct(p.metrics?.sensitivity)}
              </td>
              <td className="px-3 py-1.5 font-mono text-muted-foreground">
                {pct(p.metrics?.specificity)}
              </td>
              <td className="px-3 py-1.5 font-mono text-muted-foreground">
                {pct(p.metrics?.f1Score)}
              </td>
              <td className="px-3 py-1.5 font-mono text-muted-foreground">
                {pct(p.metrics?.mcc)}
              </td>
              <td className="px-3 py-1.5 font-mono text-muted-foreground">
                {pct(p.metrics?.balancedAccuracy)}
              </td>
              <td className="px-3 py-1.5 font-mono text-muted-foreground">
                {p.metrics?.totalResults ?? "-"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
