import { useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import type { SortingState } from "@tanstack/react-table";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import type { RecordsResponse } from "@pathfinder/shared/generated/types/RecordsResponse";
import {
  getRecords,
  type EntityRef,
} from "@/features/workbench/analysis/api/stepResults";

interface UseResultsTableRecordsArgs {
  entityRef: EntityRef;
  attributes: string[];
  sorting: SortingState;
  pageIndex: number;
  pageSize: number;
}

interface ResultsTableRecordsState {
  records: ClassifiedRecord[];
  meta: RecordsResponse["meta"] | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useResultsTableRecords({
  entityRef,
  attributes,
  sorting,
  pageIndex,
  pageSize,
}: UseResultsTableRecordsArgs): ResultsTableRecordsState {
  const queryClient = useQueryClient();

  const firstSort = sorting[0];
  const sortColumn = firstSort?.id ?? null;
  const sortDir: "ASC" | "DESC" | null = firstSort
    ? firstSort.desc
      ? "DESC"
      : "ASC"
    : null;

  const offset = pageIndex * pageSize;

  const { data, isLoading, error } = useQuery({
    queryKey: [
      "experiments",
      "records",
      entityRef.type,
      entityRef.id,
      { offset, pageSize, sortColumn, sortDir, attributes },
    ] as const,
    queryFn: () =>
      getRecords(entityRef, {
        offset,
        limit: pageSize,
        ...(sortColumn != null && sortDir != null
          ? { sort: sortColumn, dir: sortDir }
          : {}),
        attributes,
      }),
    enabled: attributes.length > 0,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
    meta: { shownInline: true },
  });

  const invalidateAndRefetch = () => {
    void queryClient.invalidateQueries({
      queryKey: ["experiments", "records", entityRef.type, entityRef.id],
    });
  };

  return {
    records: data?.records ?? [],
    meta: data?.meta ?? null,
    loading: isLoading,
    error:
      error != null ? (error instanceof Error ? error.message : String(error)) : null,
    refetch: invalidateAndRefetch,
  };
}
