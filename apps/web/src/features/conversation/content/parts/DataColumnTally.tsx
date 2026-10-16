"use client";

import type { ColumnTally } from "@pathfinder/shared";

import { ExhibitTable } from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { tableNumberFor } from "./tableNumbers";

const PAGE_SIZE = 10;

function plural(count: number, noun: string): string {
  return `${count.toLocaleString()} ${count === 1 ? noun : `${noun}s`}`;
}

function caption(data: ColumnTally): string {
  const parts = [plural(data.total, data.recordNoun), plural(data.distinct, "value")];
  const shown = (data.rows ?? []).length;
  if (shown < data.distinct) {
    parts.push(`the ${shown.toLocaleString()} with the most shown`);
  }
  return parts.join(", ");
}

export function DataColumnTally({ data }: { data: ColumnTally }) {
  const chat = useChatHelpers();
  const noun = data.recordNoun;
  return (
    <Figure
      testId="data-column-tally"
      title={data.title}
      caption={caption(data)}
      exhibit={{ kind: "table", number: tableNumberFor(chat.messages, data) }}
    >
      <ExhibitTable
        columns={[
          { head: data.columnLabel },
          { head: `${noun.charAt(0).toUpperCase()}${noun.slice(1)}s`, numeric: true },
        ]}
        pageSize={PAGE_SIZE}
        rows={(data.rows ?? []).map((row) => ({
          key: row.value,
          testId: "tally-row",
          cells: [row.value, row.count.toLocaleString()],
        }))}
      />
    </Figure>
  );
}
