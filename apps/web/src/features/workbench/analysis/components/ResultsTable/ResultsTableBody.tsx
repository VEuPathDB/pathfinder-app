import { ChevronDown, ChevronUp, ArrowUpDown, Loader2 } from "lucide-react";
import { flexRender, type Header, type Table } from "@tanstack/react-table";
import type { RecordDetailResponse } from "@pathfinder/shared/generated/types/RecordDetailResponse";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import { RecordRow } from "./RecordRow";

interface ResultsTableBodyProps {
  table: Table<ClassifiedRecord>;
  loading: boolean;
  detail: RecordDetailResponse | null;
  detailError: string | null;
  detailLoading: boolean;
  onExpandRow: (row: ClassifiedRecord, expand: boolean) => void;
}

function SortIcon({ header }: { header: Header<ClassifiedRecord, unknown> }) {
  const dir = header.column.getIsSorted();
  if (dir === "asc") return <ChevronUp className="h-3 w-3" />;
  if (dir === "desc") return <ChevronDown className="h-3 w-3" />;
  return <ArrowUpDown className="h-3 w-3 opacity-40" />;
}

export function ResultsTableBody({
  table,
  loading,
  detail,
  detailError,
  detailLoading,
  onExpandRow,
}: ResultsTableBodyProps) {
  const headerGroups = table.getHeaderGroups();
  const rows = table.getRowModel().rows;
  const columnCount = table.getVisibleLeafColumns().length + 1;

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-sm">
        <thead>
          {headerGroups.map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-border bg-muted/50">
              {headerGroup.headers.map((header) => {
                const canSort = header.column.getCanSort();
                return (
                  <th key={header.id} className="whitespace-nowrap px-4 py-2.5">
                    {canSort ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        <SortIcon header={header} />
                      </button>
                    ) : (
                      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                      </span>
                    )}
                  </th>
                );
              })}
              <th className="w-8 px-2" />
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-border">
          {loading && rows.length === 0 ? (
            <tr>
              <td colSpan={columnCount} className="py-16 text-center">
                <Loader2 className="mx-auto h-5 w-5 animate-spin text-muted-foreground" />
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td
                colSpan={columnCount}
                className="py-16 text-center text-sm text-muted-foreground"
              >
                No records found.
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <RecordRow
                key={row.id}
                row={row}
                detail={row.getIsExpanded() ? detail : null}
                detailError={row.getIsExpanded() ? detailError : null}
                detailLoading={row.getIsExpanded() && detailLoading}
                onToggle={() => onExpandRow(row.original, !row.getIsExpanded())}
              />
            ))
          )}
        </tbody>
      </table>

      {loading && rows.length > 0 && (
        <div className="flex items-center justify-center border-t border-border bg-muted/30 py-2">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      )}
    </div>
  );
}
