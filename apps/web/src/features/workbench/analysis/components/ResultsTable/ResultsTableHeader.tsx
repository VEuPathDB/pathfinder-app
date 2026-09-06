import { useRef, useState } from "react";
import { useOnClickOutside } from "usehooks-ts";
import { Columns } from "lucide-react";
import type { Table } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import type { ClassifiedRecord } from "@pathfinder/shared/generated/types/ClassifiedRecord";
import type { RecordAttribute } from "@pathfinder/shared/generated/types/RecordAttribute";
import { recordCountLabel } from "./recordCountLabel";

interface ResultsTableHeaderProps {
  totalCount: number | null;
  recordType: string | null;
  table: Table<ClassifiedRecord>;
  attributes: RecordAttribute[];
}

export function ResultsTableHeader({
  totalCount,
  recordType,
  table,
  attributes,
}: ResultsTableHeaderProps) {
  const [columnsOpen, setColumnsOpen] = useState(false);
  const columnsRef = useRef<HTMLDivElement>(null);

  useOnClickOutside(columnsRef as React.RefObject<HTMLElement>, () =>
    setColumnsOpen(false),
  );

  const displayNameByName = new Map(attributes.map((a) => [a.name, a.displayName]));

  const hideableColumns = table.getAllLeafColumns().filter((col) => col.getCanHide());

  return (
    <div className="flex items-center justify-between gap-3">
      <p className="text-xs text-muted-foreground tabular-nums">
        {recordCountLabel(totalCount, recordType)}
      </p>

      <div className="flex items-center gap-2">
        <div ref={columnsRef} className="relative">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setColumnsOpen(!columnsOpen)}
          >
            <Columns className="h-3.5 w-3.5" />
            Columns
          </Button>

          {columnsOpen && (
            <div className="absolute right-0 top-full z-30 mt-1 w-64 rounded-lg border border-border bg-popover p-2 shadow-lg">
              <div className="max-h-60 overflow-y-auto space-y-0.5">
                {hideableColumns.map((col) => (
                  <label
                    key={col.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={col.getIsVisible()}
                      onChange={col.getToggleVisibilityHandler()}
                      className="rounded border-border"
                    />
                    <span className="truncate">
                      {displayNameByName.get(col.id) ?? col.id}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
