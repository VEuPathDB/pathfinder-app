"use client";

import type { CheckWords } from "@pathfinder/shared/generated/types/CheckWords";
import type { GenomeRate } from "@pathfinder/shared/generated/types/GenomeRate";

import { EChart } from "@/lib/components/charts/EChart";
import { readChartTokens } from "@/lib/components/charts/chartTheme";

import { buildRateOption, rateRows, rateRowText } from "./rateChart.options";

export function RateChart({
  rates,
  checks,
}: {
  rates: readonly GenomeRate[];
  checks: CheckWords;
}) {
  const rows = rateRows(rates, checks);
  if (rows.length === 0) return null;
  const stated = rows.map((row) => `${row.label} ${rateRowText(row)}`).join("; ");
  return (
    <EChart
      option={buildRateOption(rows, readChartTokens())}
      height={56 + rows.length * 36}
      ariaLabel={`Error rate with its 95% interval: ${stated}`}
      testId="audit-rate-chart"
    />
  );
}
