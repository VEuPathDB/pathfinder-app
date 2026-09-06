import { useQuery } from "@tanstack/react-query";
import type { RecordDetailResponse } from "@pathfinder/shared/generated/types/RecordDetailResponse";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import {
  getRecordDetail,
  type EntityRef,
} from "@/features/workbench/analysis/api/stepResults";

interface UseResultsTableDetailArgs {
  entityRef: EntityRef;
  expandedKey: string | null;
  recordId: ClassifiedRecord["id"] | null;
}

interface ResultsTableDetailState {
  detail: RecordDetailResponse | null;
  detailError: string | null;
  detailLoading: boolean;
}

export function useResultsTableDetail({
  entityRef,
  expandedKey,
  recordId,
}: UseResultsTableDetailArgs): ResultsTableDetailState {
  const enabled = expandedKey != null && recordId != null;

  const { data, error, isPending } = useQuery({
    queryKey: [
      "experiments",
      "records",
      entityRef.type,
      entityRef.id,
      { detail: true, key: expandedKey },
    ] as const,
    queryFn: () => {
      if (recordId == null) {
        throw new Error("recordId must be set when fetching detail");
      }
      return getRecordDetail(entityRef, recordId);
    },
    enabled,
  });

  return {
    detail: data ?? null,
    detailError: error
      ? error instanceof Error
        ? error.message
        : "Failed to load record details"
      : null,
    detailLoading: isPending && enabled,
  };
}
