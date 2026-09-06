import { useSuspenseQuery, useQueryClient } from "@tanstack/react-query";
import type { DistributionResponse } from "@pathfinder/shared/generated/types/DistributionResponse";
import {
  distributionOptions,
  getDistribution,
  type EntityRef,
} from "@/features/workbench/analysis/api/stepResults";
import type { DistributionEntry } from "@/features/workbench/analysis/components/DistributionExplorer/types";
import { APIError } from "@/lib/api/http";

export function parseDistribution(raw: DistributionResponse): DistributionEntry[] {
  const firstBinStart = raw.histogram[0]?.binStart ?? "";
  const isNumericBinned = firstBinStart !== "";
  const parsed: DistributionEntry[] = raw.histogram
    .filter((bin) => (bin.value ?? 0) > 0)
    .map((bin) => {
      const label = bin.binLabel ?? "";
      const start = bin.binStart ?? "";
      return {
        value: label !== "" ? label : start,
        count: bin.value ?? 0,
      };
    });
  return isNumericBinned ? parsed : parsed.sort((a, b) => b.count - a.count);
}

const EMPTY_DISTRIBUTION: DistributionResponse = {
  histogram: [],
  statistics: {
    subsetSize: 0,
    subsetMin: null,
    subsetMax: null,
    subsetMean: null,
    numVarValues: 0,
    numDistinctValues: 0,
    numDistinctEntityRecords: 0,
    numMissingCases: 0,
  },
};

interface DistributionDataState {
  distribution: DistributionEntry[];
  noData: boolean;
  refresh: () => void;
}

export function useDistributionData(
  entityRef: EntityRef,
  selectedAttr: string,
): DistributionDataState {
  const queryClient = useQueryClient();

  const { enabled: _enabled, ...distOpts } = distributionOptions(
    entityRef,
    selectedAttr,
  );

  const { data } = useSuspenseQuery({
    ...distOpts,
    queryFn: async () => {
      try {
        return await getDistribution(entityRef, selectedAttr);
      } catch (err) {
        if (err instanceof APIError && (err.status === 404 || err.status === 422)) {
          return EMPTY_DISTRIBUTION;
        }
        throw err;
      }
    },
    select: parseDistribution,
  });

  const distribution = data;

  const refresh = () => {
    void queryClient.invalidateQueries({
      queryKey: distOpts.queryKey,
    });
  };

  return {
    distribution,
    noData: distribution.length === 0 && selectedAttr !== "",
    refresh,
  };
}
