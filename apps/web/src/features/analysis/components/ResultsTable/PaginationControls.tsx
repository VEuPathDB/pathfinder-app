import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Table } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import { PAGE_SIZE_OPTIONS } from "./ResultsTableColumns";

interface PaginationControlsProps {
  table: Table<ClassifiedRecord>;
  totalCount: number | null;
  loading: boolean;
}

export function PaginationControls({
  table,
  totalCount,
  loading,
}: PaginationControlsProps) {
  const { pageIndex, pageSize } = table.getState().pagination;
  const currentPage = pageIndex + 1;
  const totalPages =
    totalCount == null ? null : Math.max(1, Math.ceil(totalCount / pageSize));
  const hasPrev = pageIndex > 0;
  // Without a total, a full page is the only evidence that more rows exist.
  const hasNext =
    totalCount == null
      ? table.getRowModel().rows.length === pageSize
      : (pageIndex + 1) * pageSize < totalCount;

  return (
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      <div className="flex items-center gap-2">
        <span>Rows per page</span>
        <select
          value={pageSize}
          onChange={(e) => {
            table.setPageSize(Number(e.target.value));
            table.setPageIndex(0);
          }}
          className="rounded-md border border-border bg-background px-2 py-1 text-xs"
        >
          {PAGE_SIZE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <span className="tabular-nums">
          {totalPages == null
            ? `Page ${currentPage}`
            : `Page ${currentPage} of ${totalPages}`}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            disabled={!hasPrev || loading}
            onClick={() => table.previousPage()}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7"
            disabled={!hasNext || loading}
            onClick={() => table.nextPage()}
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
