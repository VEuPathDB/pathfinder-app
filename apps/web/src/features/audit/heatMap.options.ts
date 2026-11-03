import type { EChartsOption, TooltipComponentFormatterCallbackParams } from "echarts";
import { format } from "echarts/core";
import type { AuditRunView } from "@pathfinder/shared/generated/types/AuditRunView";
import type { AuditWords } from "@pathfinder/shared/generated/types/AuditWords";
import type { GenomeRate } from "@pathfinder/shared/generated/types/GenomeRate";

import type { ChartTokens } from "@/lib/components/charts/chartTheme";
import { UNRESOLVED_SERIES_COLOR } from "@/lib/components/charts/unresolved";

import { gapText, percent, rateText, shareText } from "./format";

type CheckKey = GenomeRate["check"];

export interface HeatCell {
  genome: number;
  check: number;
  value: number | null;
  stated: string | null;
  share: string | null;
  errors: string[];
}

export interface Heat {
  organisms: string[];
  genomes: string[];
  checks: CheckKey[];
  cells: HeatCell[];
}

function errorTitles(
  view: AuditRunView,
  words: AuditWords,
  genome: string,
  check: CheckKey,
): string[] {
  const titles = view.sampleCounts.flatMap((row) =>
    row.genome === genome &&
    row.check === check &&
    row.modelGenome === genome &&
    row.errorType !== null
      ? [words.errorTypes[row.errorType]]
      : [],
  );
  return [...new Set(titles)];
}

function genomeLabel(view: AuditRunView, organism: string): string {
  const genome = view.genomes.find((row) => row.organism === organism);
  return genome === undefined ? organism : `${organism} (BUSCO gap ${gapText(genome)})`;
}

export function heatCells(view: AuditRunView, words: AuditWords): Heat {
  const organisms = [...new Set(view.rates.map((rate) => rate.genome))];
  const checks = [...new Set(view.rates.map((rate) => rate.check))];
  const cells = organisms.flatMap((organism, genome) =>
    checks.map((checkKey, check) => {
      const bounds =
        view.rates.find((rate) => rate.genome === organism && rate.check === checkKey)
          ?.bounds ?? null;
      return {
        genome,
        check,
        value: bounds?.rate ?? null,
        stated: bounds === null ? null : rateText(bounds),
        share: bounds === null ? null : shareText(bounds),
        errors: errorTitles(view, words, organism, checkKey),
      };
    }),
  );
  return {
    organisms,
    genomes: organisms.map((organism) => genomeLabel(view, organism)),
    checks,
    cells,
  };
}

function cellTooltip(heat: Heat, cell: HeatCell, words: AuditWords): string {
  const check = heat.checks[cell.check];
  const lines = [
    format.encodeHTML(heat.organisms[cell.genome] ?? ""),
    check === undefined ? "" : words.checks[check],
    ...(cell.stated === null
      ? ["No judged finding"]
      : [cell.stated, cell.share ?? "", ...cell.errors]),
  ];
  return lines.join("<br/>");
}

export function buildHeatOption(
  heat: Heat,
  words: AuditWords,
  tokens: ChartTokens,
): EChartsOption {
  return {
    animation: false,
    grid: { left: 16, right: 24, top: 8, bottom: 32, containLabel: true },
    xAxis: {
      type: "category",
      data: heat.checks.map((check) => words.checks[check]),
      axisLabel: { interval: 0, overflow: "break", width: 160 },
    },
    yAxis: { type: "category", inverse: true, data: heat.genomes },
    visualMap: {
      show: false,
      min: 0,
      max: 1,
      inRange: { color: [tokens.card, tokens.series[0] ?? UNRESOLVED_SERIES_COLOR] },
    },
    tooltip: {
      trigger: "item",
      formatter: (params: TooltipComponentFormatterCallbackParams) => {
        const entry = Array.isArray(params) ? params[0] : params;
        const cell = entry === undefined ? undefined : heat.cells[entry.dataIndex];
        return cell === undefined ? "" : cellTooltip(heat, cell, words);
      },
    },
    series: [
      {
        type: "heatmap",
        label: {
          show: true,
          color: tokens.foreground,
          formatter: (entry) => {
            const cell = heat.cells[entry.dataIndex];
            return cell?.value == null ? "" : percent(cell.value);
          },
        },
        data: heat.cells.map((cell) => [cell.check, cell.genome, cell.value]),
      },
    ],
  };
}
