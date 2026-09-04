"use client";

import { useQuery } from "@tanstack/react-query";
import type { EdaFilter } from "@pathfinder/shared/generated/types/EdaFilter";
import type { EdaVariableResponse } from "@pathfinder/shared/generated/types/EdaVariableResponse";

import { BarChart } from "@/lib/components/charts/BarChart";
import { HistogramChart } from "@/lib/components/charts/HistogramChart";
import { edaDistribution } from "@/features/eda/api";

const HEIGHT = 96;
const SERIES_NAME = "Subset";
const MULTIVALUED_NOTE =
  "one record can carry several values, so these counts do not add up to the subset size";

export interface DistributionSparklineProps {
  siteId: string;
  datasetId: string;
  variable: EdaVariableResponse;
  filters: readonly EdaFilter[];
}

export function DistributionSparkline({
  siteId,
  datasetId,
  variable,
  filters,
}: DistributionSparklineProps) {
  const distribution = useQuery({
    queryKey: [
      "eda",
      "distribution",
      siteId,
      datasetId,
      variable.entityId,
      variable.variableId,
      filters,
    ] as const,
    queryFn: () =>
      edaDistribution({
        siteId,
        datasetId,
        entityId: variable.entityId,
        variableId: variable.variableId,
        filters: [...filters],
      }),
  });

  if (distribution.error != null) {
    return (
      <p
        data-testid="eda-subset-distribution-error"
        className="text-[11px] text-muted-foreground"
      >
        distribution unavailable
      </p>
    );
  }
  const series = distribution.data;
  if (series === undefined) return null;

  const { subsetSize, numVarValues, numMissingCases } = series;
  const chartSeries = [
    { name: SERIES_NAME, labels: series.labels, values: series.values },
  ];
  const continuous = variable.dataShape === "continuous";

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium">{series.variableDisplayName}</p>
      {continuous ? (
        <HistogramChart
          series={chartSeries}
          barMode="stack"
          valueLabel="Records"
          height={HEIGHT}
          testId="eda-subset-sparkline-histogram"
        />
      ) : (
        <BarChart
          series={chartSeries}
          barMode="group"
          valueLabel="Records"
          height={HEIGHT}
          testId="eda-subset-sparkline-bar"
        />
      )}
      <p
        data-testid="eda-subset-coverage"
        className="text-[11px] text-muted-foreground"
      >
        {`${numVarValues.toLocaleString("en-US")} of ${subsetSize.toLocaleString("en-US")} records have a value`}
        {numMissingCases > 0
          ? `, ${numMissingCases.toLocaleString("en-US")} missing`
          : ""}
      </p>
      {series.isMultiValued ? (
        <p
          data-testid="eda-subset-multivalued"
          className="text-[11px] text-muted-foreground"
        >
          {MULTIVALUED_NOTE}
        </p>
      ) : null}
    </div>
  );
}
