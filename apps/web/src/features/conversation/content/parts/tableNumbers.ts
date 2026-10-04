import type { UIMessage } from "ai";
import type {
  ControlTestResults,
  EdaStatisticsPart,
  ScoredComparison,
  VariantComparison,
} from "@pathfinder/shared";
import { edaStatisticsPartSchema } from "@pathfinder/shared/generated/zod/edaStatisticsPartSchema";

import { isCurrentWire } from "../currentWire";
import { statisticExhibitKind } from "./statisticExhibit";

/** A part the thread numbers as a paper table. */
export type TableExhibit =
  ControlTestResults | EdaStatisticsPart | ScoredComparison | VariantComparison;

/** The one table kind a durable task produces. */
const CONTROL_TESTS = "data-control-test-results";

const TABLE_KINDS: ReadonlySet<string> = new Set([
  CONTROL_TESTS,
  "data-scored-comparison",
  "data-variant-comparison",
]);

const STATISTICS = "data-eda.statistics";

/** Whether the part reads as a table. A statistic does when it charts nothing
 * and the current wire carries it. */
function isTable(type: string, data: unknown): data is object {
  if (type === STATISTICS) {
    return (
      isCurrentWire(edaStatisticsPartSchema, data) &&
      statisticExhibitKind(data) === "table"
    );
  }
  return TABLE_KINDS.has(type) && typeof data === "object" && data !== null;
}

/** What one durable task's exhibit answers: its number, and the call whose
 * summary line describes it. */
export interface TaskTable {
  number: number;
  toolCallId: string | null;
}

/** The thread's tabular exhibits, in emission order. */
function tablesOf(messages: readonly UIMessage[]): { type: string; data: object }[] {
  const tables: { type: string; data: object }[] = [];
  for (const message of messages) {
    for (const part of message.parts) {
      if (!("data" in part) || !isTable(part.type, part.data)) continue;
      tables.push({ type: part.type, data: part.data });
    }
  }
  return tables;
}

/**
 * The 1-based number of this exhibit among the thread's tables. The payload
 * the thread holds is the identity, so two exhibits with equal contents take
 * two numbers and a number never moves while the turn streams. Null when the
 * thread does not carry the payload.
 */
export function tableNumberFor(
  messages: readonly UIMessage[],
  data: TableExhibit,
): number | null {
  const index = tablesOf(messages).findIndex((table) => table.data === data);
  return index === -1 ? null : index + 1;
}

/** The exhibit one durable task left on the thread, or null when it left none. */
export function tablePartFor(
  messages: readonly UIMessage[],
  taskId: string,
): TaskTable | null {
  const tables = tablesOf(messages);
  const index = tables.findIndex(
    (table) =>
      table.type === CONTROL_TESTS &&
      "taskId" in table.data &&
      table.data.taskId === taskId,
  );
  const found = tables[index];
  if (found === undefined) return null;
  const call = "toolCallId" in found.data ? found.data.toolCallId : null;
  return {
    number: index + 1,
    toolCallId: typeof call === "string" && call !== "" ? call : null,
  };
}
