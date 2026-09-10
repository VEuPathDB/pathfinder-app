"use client";

import type { UIMessage } from "ai";
import type { ReactElement, ReactNode } from "react";
import {
  buildTrace,
  isToolPart,
  turnUsage,
  type MessagePart,
} from "@veupathdb/assistant-client";
import { toTraceParts } from "@veupathdb/assistant-client/ai-sdk";
import type { DataSubAgentCallPayload } from "@pathfinder/shared";
import { subAgentCallPayloadSchema } from "@pathfinder/shared/generated/zod/subAgentCallPayloadSchema";

import { parseModelString } from "@/lib/models/providerMeta";
import {
  Trace,
  type TraceRunView,
  type TraceUsageView,
} from "@/features/conversation/thread/Trace";
import { humanizeToolName } from "@/features/conversation/toolNames";

import { ToolApprovalControls } from "../content/parts/ToolApprovalControls";
import { useChatHelpers, type ChatHelpers } from "../runtime/chatHelpersContext";
import { traceRenderingKinds } from "./traceRenderingKinds";
import { useThreadDevMode, type ThreadDevMode } from "./useThreadDevMode";

type Run = ReturnType<typeof buildTrace>[number];

const LEAD = "lead";
const SUB_AGENT_KIND = "data-sub-agent-call";
const LIVE: readonly ChatHelpers["status"][] = ["submitted", "streaming"];

export interface TraceAnchorProps {
  toolCallId: string;
  toolName: string;
  args: unknown;
  result?: unknown;
  status: { type: "running" | "complete" | "incomplete" | "requires-action" };
}

/** A dispatch payload the wire's own schema accepts, or null. */
function readSubAgentCall(data: unknown): DataSubAgentCallPayload | null {
  const parsed = subAgentCallPayloadSchema.safeParse(data);
  return parsed.success ? parsed.data : null;
}

/**
 * The turn's model, tokens and cost: the Lead's own usage plus every
 * sub-agent it dispatched, which is what the wire reports as the turn total.
 */
export function turnUsageOf(parts: readonly MessagePart[]): TraceUsageView | null {
  const usage = turnUsage(parts);
  if (usage.lead === null) return null;
  const { model } = parseModelString(usage.modelId ?? "");
  if (model === "") return null;
  return {
    model,
    tokens: usage.total.tokens,
    costUsd: String(usage.total.costUsd),
  };
}

/** The id a part anchors, or null when the part bears no row of its own. */
function anchorIdOf(part: MessagePart): string | null {
  if (isToolPart(part)) return part.toolCallId;
  if (part.type === SUB_AGENT_KIND)
    return readSubAgentCall(part.data)?.toolCallId ?? null;
  return null;
}

function idsOf(run: Run): Set<string> {
  const ids = new Set<string>();
  for (const group of run.groups) {
    if (group.key !== LEAD) ids.add(group.key);
    for (const row of group.rows) ids.add(row.toolCallId);
  }
  return ids;
}

function firstAnchorOf(
  parts: readonly MessagePart[],
  ids: ReadonlySet<string>,
): string | null {
  for (const part of parts) {
    const id = anchorIdOf(part);
    if (id !== null && ids.has(id)) return id;
  }
  return null;
}

/** Every approval the run carries. A row with none renders nothing. */
function approvalsOf(run: TraceRunView): ReactNode {
  return run.groups
    .flatMap((group) => group.rows)
    .map((row) => (
      <ToolApprovalControls key={row.toolCallId} toolCallId={row.toolCallId} />
    ));
}

function drawRun(
  run: TraceRunView,
  dev: ThreadDevMode,
  usage: TraceUsageView | null,
): ReactElement {
  return (
    <Trace
      run={run}
      showRaw={dev.showRaw}
      showUsage={dev.showUsage}
      nameFor={humanizeToolName}
      approval={approvalsOf(run)}
      {...(usage === null ? {} : { usage })}
    />
  );
}

/** Every turn is over but the live one, which is the thread's last message. */
function turnEnded(chat: ChatHelpers, message: UIMessage): boolean {
  if (!LIVE.includes(chat.status)) return true;
  return chat.messages.at(-1) !== message;
}

/**
 * Draw the whole run the anchored part belongs to, and only at the run's first
 * row-bearing part, so a turn's calls read as one block wherever they arrived.
 */
function anchored(
  chat: ChatHelpers,
  anchorId: string,
  dev: ThreadDevMode,
): ReactElement | null {
  for (const message of chat.messages) {
    const parts = toTraceParts(message.parts);
    if (!parts.some((part) => anchorIdOf(part) === anchorId)) continue;
    const runs = buildTrace(parts, {
      renderingKinds: traceRenderingKinds(),
      turnEnded: turnEnded(chat, message),
    });
    const index = runs.findIndex((each) => idsOf(each).has(anchorId));
    const run = runs[index];
    if (run === undefined) return null;
    if (firstAnchorOf(parts, idsOf(run)) !== anchorId) return null;
    // The turn's totals close the turn, so they ride its last run alone.
    const usage = index === runs.length - 1 ? turnUsageOf(parts) : null;
    return drawRun(run, dev, usage);
  }
  return null;
}

export function TraceAnchor(props: TraceAnchorProps): ReactElement | null {
  const chat = useChatHelpers();
  const dev = useThreadDevMode();
  return anchored(chat, props.toolCallId, dev);
}

export function SubAgentTraceAnchor({
  data,
}: {
  data: DataSubAgentCallPayload;
}): ReactElement | null {
  const chat = useChatHelpers();
  const dev = useThreadDevMode();
  const call = readSubAgentCall(data);
  if (call === null) return null;
  return anchored(chat, call.toolCallId, dev);
}
