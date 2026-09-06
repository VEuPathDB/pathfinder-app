import { ChevronDown, ChevronUp } from "lucide-react";
import { flexRender, type Row } from "@tanstack/react-table";
import type { RecordDetailResponse } from "@pathfinder/shared/generated/types/RecordDetailResponse";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import { ExpandedRowDetail } from "./ExpandedRowDetail";

interface RecordRowProps {
  row: Row<ClassifiedRecord>;
  detail: RecordDetailResponse | null;
  detailError: string | null;
  detailLoading: boolean;
  onToggle: () => void;
}

export function RecordRow({
  row,
  detail,
  detailError,
  detailLoading,
  onToggle,
}: RecordRowProps) {
  const isExpanded = row.getIsExpanded();
  const visibleCells = row.getVisibleCells();
  const colSpan = visibleCells.length + 1;
  const pk = row.id;

  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer transition-colors hover:bg-accent/50 data-[expanded=true]:bg-accent/30"
        data-expanded={isExpanded}
      >
        {visibleCells.map((cell) => (
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
