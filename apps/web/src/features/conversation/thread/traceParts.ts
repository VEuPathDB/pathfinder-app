import {
  isCustomContentUIPart,
  isDynamicToolUIPart,
  isReasoningFileUIPart,
  isToolUIPart,
  type ToolUIPart,
  type UIMessage,
} from "ai";
import type {
  MessagePart,
  ToolPart,
  ToolSummaryStatus,
} from "@pathfinder/assistant-client";
import { toolSummaryPayloadSchema } from "@pathfinder/shared/generated/zod/toolSummaryPayloadSchema";

type UIPart = UIMessage["parts"][number];

interface Line {
  summary?: string;
  summaryStatus?: ToolSummaryStatus;
}

/**
 * The line a tool wrote about its own call, when the reducer folded it on. The
 * wire's own schema decides what counts as a line, so a malformed one is no
 * line at all.
 */
function lineOf(part: ToolUIPart): Line {
  const held: Record<string, unknown> = { ...part };
  const parsed = toolSummaryPayloadSchema.safeParse({
    toolCallId: part.toolCallId,
    summary: held["summary"],
    status: held["summaryStatus"],
  });
  if (!parsed.success) return {};
  const status = parsed.data.status;
  if (status === undefined) return { summary: parsed.data.summary };
  return { summary: parsed.data.summary, summaryStatus: status };
}

function toolPart(part: ToolUIPart): ToolPart {
  const head = { type: part.type, toolCallId: part.toolCallId, ...lineOf(part) };
  switch (part.state) {
    case "input-streaming":
    case "input-available":
      return { ...head, state: part.state, input: part.input };
    case "approval-requested":
      return {
        ...head,
        state: "approval-requested",
        input: part.input,
        approval: { id: part.approval.id },
      };
    case "approval-responded":
      return { ...head, state: "input-available", input: part.input };
    case "output-available":
      return {
        ...head,
        state: "output-available",
        input: part.input,
        output: part.output,
      };
    case "output-error":
      return {
        ...head,
        state: "output-error",
        input: part.input,
        errorText: part.errorText,
      };
    case "output-denied":
      return {
        ...head,
        state: "output-denied",
        input: part.input,
        approval: { id: part.approval.id, approved: false },
      };
  }
}

type ProtocolPart = Exclude<
  UIPart,
  { type: "custom" | "reasoning-file" | "dynamic-tool" }
>;

/** Report whether the protocol's chunk vocabulary names this part's kind. */
function isProtocolPart(part: UIPart): part is ProtocolPart {
  return !(
    isCustomContentUIPart(part) ||
    isReasoningFileUIPart(part) ||
    isDynamicToolUIPart(part)
  );
}

/**
 * Read a message's parts as the protocol shape `buildTrace` walks. The SDK's
 * own reducer leaves a tool's summary beside its call; ours folds it on, and
 * both shapes reach the trace unchanged.
 */
export function toTraceParts(parts: readonly UIPart[]): MessagePart[] {
  const out: MessagePart[] = [];
  for (const part of parts) {
    if (!isProtocolPart(part)) continue;
    if (isToolUIPart(part)) {
      out.push(toolPart(part));
      continue;
    }
    out.push(part);
  }
  return out;
}
