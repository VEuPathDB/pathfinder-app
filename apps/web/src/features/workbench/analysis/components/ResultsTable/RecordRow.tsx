import { ChevronDown, ChevronUp } from "lucide-react";
import { flexRender, type Cell } from "@tanstack/react-table";
import type { RecordDetailResponse } from "@pathfinder/shared/generated/types/RecordDetailResponse";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import { ExpandedRowDetail } from "./ExpandedRowDetail";
import type { ResultsTableFeatures } from "./resultsTableFeatures";

interface RecordRowProps {
  pk: string;
  // Table state arrives as props. A read through the row object is cached on
  // the row identity, which the table keeps across a state change.
  cells: Cell<ResultsTableFeatures, ClassifiedRecord, unknown>[];
  isExpanded: boolean;
  detail: RecordDetailResponse | null;
  detailError: string | null;
  detailLoading: boolean;
  onToggle: () => void;
}

export function RecordRow({
  pk,
  cells,
  isExpanded,
  detail,
  detailError,
  detailLoading,
  onToggle,
}: RecordRowProps) {
  const colSpan = cells.length + 1;

  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer transition-colors hover:bg-accent/50 data-[expanded=true]:bg-accent/30"
        data-expanded={isExpanded}
      >
        {cells.map((cell) => (
          <td
            key={cell.id}
            className="max-w-[300px] truncate px-4 py-2 text-sm text-foreground"
          >
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </td>
        ))}
        <td className="px-2 py-2 text-muted-foreground">
          {isExpanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </td>
      </tr>
      <tr>
        <td colSpan={colSpan} className="p-0">
          <div
            className="overflow-hidden transition-all duration-200 ease-in-out"
            style={{
              maxHeight: isExpanded ? "500px" : "0px",
              opacity: isExpanded ? 1 : 0,
            }}
          >
            <ExpandedRowDetail
              pk={pk}
              detail={detail}
              error={detailError}
              loading={detailLoading}
              onClose={onToggle}
            />
          </div>
        </td>
      </tr>
    </>
  );
}
