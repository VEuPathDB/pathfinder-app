"use client";

import { siteShortName, type ColumnTally } from "@pathfinder/shared";

import { ExhibitTable } from "@/features/conversation/thread/ExhibitTable";
import { Figure } from "@/features/conversation/thread/Figure";

import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { tableNumberFor } from "./tableNumbers";

const PAGE_SIZE = 10;

type TallyRow = NonNullable<ColumnTally["rows"]>[number];

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

function valueCell(row: TallyRow) {
  if (row.label === undefined || row.label === "") {
    return row.value;
  }
  return (
    <>
      <span data-testid="tally-value">{row.value}</span>{" "}
      <span data-testid="tally-label" className="text-muted-foreground">
        {row.label}
      </span>
    </>
  );
}

function stepLink(data: ColumnTally) {
  if (data.stepUrl === undefined || data.stepUrl === null || data.stepUrl === "") {
    return null;
  }
  return (
    <a
      href={data.stepUrl}
      target="_blank"
      rel="noreferrer"
      className="mt-2 block text-sm font-medium text-primary underline-offset-2 hover:underline"
    >
      {`Open this step on ${siteShortName(data.siteId)}`}
    </a>
  );
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
      footer={stepLink(data)}
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
          cells: [valueCell(row), row.count.toLocaleString()],
        }))}
      />
    </Figure>
  );
}
