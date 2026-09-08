import type { ReactElement, ReactNode } from "react";

export interface ExhibitColumn {
  head: string;
  /** Numbers sit at the right of the column and share one digit width. */
  numeric?: boolean;
}

export interface ExhibitRow {
  key: string;
  /** One cell per column, in the columns' order. */
  cells: readonly ReactNode[];
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
}: ExhibitTableProps): ReactElement {
  return (
    <div>
      <div className="overflow-x-auto">
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
            {rows.map((row) => (
              <tr key={row.key}>
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
