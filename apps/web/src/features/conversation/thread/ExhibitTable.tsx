"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type ReactElement, type ReactNode } from "react";

import { Button } from "@/components/ui/button";

export interface ExhibitColumn {
  head: string;
  /** Numbers sit at the right of the column and share one digit width. */
  numeric?: boolean;
}

export interface ExhibitRow {
  key: string;
  /** One cell per column, in the columns' order. */
  cells: readonly ReactNode[];
  testId?: string;
}

export interface ExhibitNote {
  key: string;
  label: string;
  body: ReactNode;
}

interface ExhibitTableProps {
  columns: readonly ExhibitColumn[];
  rows: readonly ExhibitRow[];
  /** Read under the table, the way a paper's table notes are. */
  notes?: readonly ExhibitNote[];
  testId?: string;
  pageSize?: number;
}

const HEAD = "border-b border-border px-3 py-1.5 font-medium text-foreground";
const CELL = "px-3 py-1.5 align-baseline text-foreground";

function align(column: ExhibitColumn): string {
  return column.numeric === true ? "text-right tabular-nums" : "text-left";
}

/** A table in the reading flow of a paper: rules above the head, under it and
 * under the body, no rules between columns, and the numbers in the body font. */
export function ExhibitTable({
  columns,
  rows,
  notes = [],
  testId,
  pageSize,
}: ExhibitTableProps): ReactElement {
  const [page, setPage] = useState(0);
  const size = pageSize ?? rows.length;
  const pages = Math.max(1, Math.ceil(rows.length / Math.max(size, 1)));
  const current = Math.min(page, pages - 1);
  const shown =
    pageSize === undefined ? rows : rows.slice(current * size, (current + 1) * size);
  return (
    <div>
      <div
        role="region"
        aria-label={`Table: ${columns.map((column) => column.head).join(", ")}`}
        tabIndex={0}
        className="overflow-x-auto"
      >
        <table
          data-testid={testId}
          className="mx-auto w-full border-collapse border-t border-b border-border text-xs"
        >
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column.head}
                  scope="col"
                  className={`${HEAD} ${align(column)}`}
                >
                  {column.head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {shown.map((row) => (
              <tr key={row.key} data-testid={row.testId}>
                {columns.map((column, index) => (
                  <td key={column.head} className={`${CELL} ${align(column)}`}>
                    {row.cells[index]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 ? (
        <div
          data-testid="exhibit-pager"
          className="mt-1 flex items-center justify-end gap-1 text-xs text-muted-foreground"
        >
          <span className="tabular-nums">
            {(current * size + 1).toLocaleString()}-
            {Math.min((current + 1) * size, rows.length).toLocaleString()} of{" "}
            {rows.length.toLocaleString()}
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="Previous page"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            <ChevronLeft aria-hidden />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="Next page"
            disabled={current === pages - 1}
            onClick={() => setPage(current + 1)}
          >
            <ChevronRight aria-hidden />
          </Button>
        </div>
      ) : null}
      {notes.length > 0 ? (
        <dl className="mt-2 space-y-0.5 text-[11px] leading-relaxed">
          {notes.map((note) => (
            <div key={note.key} className="flex gap-1.5">
              <dt className="shrink-0 text-muted-foreground">{note.label}</dt>
              <dd className="min-w-0 text-foreground">{note.body}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}
