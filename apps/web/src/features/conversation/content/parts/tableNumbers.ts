import type { UIMessage } from "ai";
import type {
  ControlTestResults,
  EnrichmentResultsChunk,
  ScoredComparison,
  VariantComparison,
} from "@pathfinder/shared";

/** A part the thread numbers as a paper table. */
export type TableExhibit =
  ControlTestResults | EnrichmentResultsChunk | ScoredComparison | VariantComparison;

const CONTROL_TESTS = "data-control-test-results";
const ENRICHMENT = "data-enrichment-results";

const TABLE_KINDS: ReadonlySet<string> = new Set([
  CONTROL_TESTS,
  ENRICHMENT,
  "data-scored-comparison",
  "data-variant-comparison",
]);

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
      if (!("data" in part) || !TABLE_KINDS.has(part.type)) continue;
      if (typeof part.data !== "object" || part.data === null) continue;
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

const TASK_KINDS: ReadonlySet<string> = new Set([CONTROL_TESTS, ENRICHMENT]);

/** The exhibit one durable task left on the thread, or null when it left none. */
export function tablePartFor(
  messages: readonly UIMessage[],
  taskId: string,
): TaskTable | null {
  const tables = tablesOf(messages);
  const index = tables.findIndex(
    (table) =>
      TASK_KINDS.has(table.type) &&
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
