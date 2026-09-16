"use client";

import type { Experiment } from "@pathfinder/shared";

import { fmtNum, pct } from "../../analysis/utils/formatters";

export interface ExperimentRow {
  /** What this run varied: an organism, or a control set. */
  label: string;
  experiment: Experiment;
}

interface ExperimentComparisonTableProps {
  /** Header of the column that names what each run varied. */
  runHeader: string;
  rows: ExperimentRow[];
  testId: string;
}

/** One row per completed run, with the metrics that compare them. */
export function ExperimentComparisonTable({
  runHeader,
  rows,
  testId,
}: ExperimentComparisonTableProps) {
  return (
    <div data-testid={testId} className="overflow-x-auto rounded-md border">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-muted-foreground">
            <th className="px-3 py-2">{runHeader}</th>
            <th className="px-3 py-2 text-right">Genes</th>
            <th className="px-3 py-2 text-right">Precision</th>
            <th className="px-3 py-2 text-right">Recall</th>
            <th className="px-3 py-2 text-right">F1</th>
            <th className="px-3 py-2 text-right">MCC</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ label, experiment }) => (
            <tr
              key={experiment.id}
              data-testid="experiment-row"
              data-run={label}
              className="border-b last:border-0"
            >
              <td className="px-3 py-1.5">{label}</td>
              {experiment.metrics == null ? (
                <td className="px-3 py-1.5 text-destructive" colSpan={5}>
                  {experiment.error ?? "No metrics: this run produced no results."}
                </td>
              ) : (
                <>
                  <td className="px-3 py-1.5 text-right">
                    {experiment.metrics.totalResults ?? 0}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {pct(experiment.metrics.precision)}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {pct(experiment.metrics.sensitivity)}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {pct(experiment.metrics.f1Score)}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {fmtNum(experiment.metrics.mcc, 2)}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
