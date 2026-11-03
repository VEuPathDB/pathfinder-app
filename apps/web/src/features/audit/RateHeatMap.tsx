"use client";

import type { AuditRunView } from "@pathfinder/shared/generated/types/AuditRunView";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";

import { EChart } from "@/lib/components/charts/EChart";
import { readChartTokens } from "@/lib/components/charts/chartTheme";

import {
  buildHeatOption,
  heatCells,
  type Heat,
  type HeatCell,
} from "./heatMap.options";

function cellText(heat: Heat, cell: HeatCell, words: AuditWords): string {
  const check = heat.checks[cell.check];
  const named = `${heat.organisms[cell.genome] ?? ""}, ${check === undefined ? "" : words.checks[check]} ${cell.stated ?? ""}`;
  return [named, cell.share ?? "", ...cell.errors].join(", ");
}

export function RateHeatMap({
  view,
  words,
}: {
  view: AuditRunView;
  words: AuditWords;
}) {
  if (view.rates.length === 0) return null;
  const heat = heatCells(view, words);
  const stated = heat.cells
    .filter((cell) => cell.stated !== null)
    .map((cell) => cellText(heat, cell, words))
    .join("; ");
  return (
    <EChart
      option={buildHeatOption(heat, words, readChartTokens())}
      height={64 + 40 * heat.genomes.length}
      ariaLabel={`Error rate by screened genome and check: ${stated}`}
      testId="audit-rate-heat-map"
    />
  );
}
