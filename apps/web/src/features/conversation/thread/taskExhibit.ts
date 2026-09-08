import type { UIMessage } from "ai";
import { subAgentStepPayloadSchema } from "@pathfinder/shared/generated/zod/subAgentStepPayloadSchema";
import { toolSummaryPayloadSchema } from "@pathfinder/shared/generated/zod/toolSummaryPayloadSchema";

import { tablePartFor } from "../content/parts/tableNumbers";
import { exhibitAnchorId, exhibitLabel } from "./exhibits";

/** Where a row's cross-reference points, and how it reads. */
export interface TaskReference {
  label: string;
  href: string;
}

/** What a finished task's row reads off the thread. */
export interface TaskResult {
  /** The line the tool wrote about this call, when the thread carries one. */
  summary: string | null;
  reference: TaskReference | null;
}

type Part = UIMessage["parts"][number];

/**
 * The line one tool call wrote about itself. The Lead's calls carry it as a
 * summary part of its own; a sub-agent's calls carry it on the step row,
 * because no reducer on the main stream holds an inner call.
 */
function lineFor(part: Part, toolCallId: string): string | null {
  if (part.type === "data-tool-summary") {
    const parsed = toolSummaryPayloadSchema.safeParse(part.data);
    if (!parsed.success || parsed.data.toolCallId !== toolCallId) return null;
    return parsed.data.summary;
  }
  if (part.type !== "data-sub-agent-step") return null;
  const step = subAgentStepPayloadSchema.safeParse(part.data);
  if (!step.success || step.data.toolCallId !== toolCallId) return null;
  const summary = step.data.resultSummary ?? "";
  return summary === "" ? null : summary;
}

function summaryFor(messages: readonly UIMessage[], toolCallId: string): string | null {
  let found: string | null = null;
  for (const message of messages) {
    for (const part of message.parts) {
      found = lineFor(part, toolCallId) ?? found;
    }
  }
  return found;
}

/** The summary line and the exhibit cross-reference of one durable task. */
export function taskResult(messages: readonly UIMessage[], taskId: string): TaskResult {
  const table = tablePartFor(messages, taskId);
  if (table === null) return { summary: null, reference: null };
  return {
    summary: table.toolCallId === null ? null : summaryFor(messages, table.toolCallId),
    reference: {
      label: `see ${exhibitLabel("table", table.number)}`,
      href: `#${exhibitAnchorId("table", table.number)}`,
    },
  };
}
