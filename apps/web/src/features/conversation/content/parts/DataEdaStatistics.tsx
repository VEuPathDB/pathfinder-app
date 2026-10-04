"use client";

import type { EdaStatisticsPart } from "@pathfinder/shared";
import type { EdaCountTable } from "@pathfinder/shared/generated/types/EdaCountTable";
import type { EdaStatisticRow } from "@pathfinder/shared/generated/types/EdaStatisticRow";
import type { EdaTrend } from "@pathfinder/shared/generated/types/EdaTrend";
import { edaStatisticsPartSchema } from "@pathfinder/shared/generated/zod/edaStatisticsPartSchema";

import { ExhibitTable } from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";
import { BoxplotChart } from "@/lib/components/charts/BoxplotChart";
import { ScatterChart } from "@/lib/components/charts/ScatterChart";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { StalePartNotice } from "../StalePartNotice";
import { isCurrentWire } from "../currentWire";
import { studyNameFor } from "./analysisStateParts";
import { figureNumberFor } from "./figureNumbers";
import { plotCaption } from "./plotCaptions";
import { statisticExhibitKind } from "./statisticExhibit";
import { tableNumberFor } from "./tableNumbers";

const BOXPLOT_HEIGHT = 240;
const TREND_HEIGHT = 280;
const NOT_REPORTED = "not reported";

const ROW_COLUMNS = [
  { head: "Statistic" },
  { head: "Value", numeric: true },
  { head: "p-value", numeric: true },
  { head: "Confidence interval", numeric: true },
];

export function DataEdaStatistics({ data }: { data: unknown }) {
  if (!isCurrentWire(edaStatisticsPartSchema, data)) {
    return <StalePartNotice subject="A statistic" />;
  }
  return <StatisticsFigure data={data} />;
}

function counted(count: number, noun: string): string {
  return `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;
}

/** The n the statistic rests on: the records a table counts, the points a
 * trend fits, or the groups a box plot draws. */
function statisticCount(data: EdaStatisticsPart): string {
  if (data.table !== null) {
    const total = data.table.matrix.flat().reduce((sum, cell) => sum + cell, 0);
    return counted(total, "record");
  }
  if (data.trend !== null) return counted(data.trend.x.length, "point");
  return counted(data.boxes.length, "group");
}

function StatisticsFigure({ data }: { data: EdaStatisticsPart }) {
  const chat = useChatHelpers();
  const kind = statisticExhibitKind(data);
  const number =
    kind === "figure"
      ? figureNumberFor(chat.messages, data)
      : tableNumberFor(chat.messages, data);
  const study = studyNameFor(chat.messages, data.analysisId);

  return (
    <Figure
      testId="data-eda-statistics"
      title={data.title}
      caption={plotCaption(data.caption ?? "", study, statisticCount(data))}
      exhibit={{ kind, number }}
    >
      <div className="space-y-3">
        {data.table !== null ? <CountTable table={data.table} /> : null}
        {data.boxes.length > 0 ? (
          <BoxplotChart
            boxes={data.boxes}
            height={BOXPLOT_HEIGHT}
            testId="eda-statistics-boxplot"
          />
        ) : null}
        {data.trend !== null ? <TrendChart trend={data.trend} /> : null}
        {data.rows.length > 0 ? <StatisticRows rows={data.rows} /> : null}
      </div>
    </Figure>
  );
}

function reported(text: string | null) {
  return text ?? <span className="text-muted-foreground">{NOT_REPORTED}</span>;
}

/** Each x label as a row and each y label as a column. */
function CountTable({ table }: { table: EdaCountTable }) {
  return (
    <ExhibitTable
      testId="eda-statistics-counts"
      columns={[
        { head: "" },
        ...table.yLabels.map((label) => ({ head: label, numeric: true })),
      ]}
      rows={table.xLabels.map((label, i) => ({
        key: label,
        testId: `eda-statistics-count-${String(i)}`,
        cells: [
          label,
          ...table.yLabels.map((_, j) => {
            const count = table.matrix[i]?.[j];
            return count === undefined ? reported(null) : count.toLocaleString();
          }),
        ],
      }))}
    />
  );
}

function StatisticRows({ rows }: { rows: readonly EdaStatisticRow[] }) {
  return (
    <ExhibitTable
      testId="eda-statistics-rows"
      columns={ROW_COLUMNS}
      rows={rows.map((row, i) => ({
        key: row.name,
        testId: `eda-statistics-row-${String(i)}`,
        cells: [
          row.name,
          reported(row.value),
          reported(row.pValue),
          reported(row.confidenceInterval),
        ],
      }))}
    />
  );
}

function TrendChart({ trend }: { trend: EdaTrend }) {
  return (
    <ScatterChart
      series={[{ name: "Points", x: trend.x, y: trend.y }]}
      line={{ name: "Best-fit line", x: trend.lineX, y: trend.lineY }}
      xAxis={{ variableId: "x", displayName: trend.xLabel }}
      yAxis={{ variableId: "y", displayName: trend.yLabel }}
      height={TREND_HEIGHT}
      testId="eda-statistics-trend"
    />
  );
}
