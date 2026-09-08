import {
  type ReactTable,
  columnVisibilityFeature,
  createExpandedRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  rowExpandingFeature,
  rowPaginationFeature,
  rowSortingFeature,
  tableFeatures,
} from "@tanstack/react-table";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";

/** The table features the results table registers, and nothing else. */
export const resultsTableFeatures = tableFeatures({
  columnVisibilityFeature,
  rowSortingFeature,
  rowPaginationFeature,
  rowExpandingFeature,
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  expandedRowModel: createExpandedRowModel(),
});

export type ResultsTableFeatures = typeof resultsTableFeatures;

export type ResultsTableInstance = ReactTable<ResultsTableFeatures, ClassifiedRecord>;
