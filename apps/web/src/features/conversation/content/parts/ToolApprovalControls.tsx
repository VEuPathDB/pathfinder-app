"use client";

import { getToolName, isToolUIPart, type ToolUIPart, type UIMessage } from "ai";
import type { ReactElement } from "react";
import { toast } from "sonner";
import { toolSummaryPayloadSchema } from "@pathfinder/shared/generated/zod/toolSummaryPayloadSchema";

import {
  ApprovalCard,
  type ApprovalDecision,
} from "@/features/conversation/thread/ApprovalCard";
import {
  approvalPromptFor,
  approvalSubjectFor,
} from "@/features/conversation/toolNames";

import {
  ADOPTION_TOOL_NAME,
  CONSULT_TOOL_NAME,
  PROPOSAL_TOOL_NAME,
} from "../../rail/consultActions";
import { useChatHelpers } from "../../runtime/chatHelpersContext";
import { useThreadDevMode } from "../../thread/useThreadDevMode";

/** The tools whose approval their own card answers. */
const CARD_TOOLS: ReadonlySet<string> = new Set([
  CONSULT_TOOL_NAME,
  PROPOSAL_TOOL_NAME,
  ADOPTION_TOOL_NAME,
]);

export interface ToolApprovalView {
  approvalId: string;
  toolName: string;
  input: ToolUIPart["input"];
  decision: ApprovalDecision;
  /** The first line the thread holds for this call: the one written when it asked. */
  asked: string | null;
}

function decisionOf(
  state: ToolUIPart["state"],
  approved: boolean | undefined,
): ApprovalDecision {
  if (state === "approval-requested") return "pending";
  return approved === true ? "approved" : "denied";
}

function firstSummaryLine(messages: UIMessage[], toolCallId: string): string | null {
  for (const message of messages) {
    for (const part of message.parts) {
      if (part.type !== "data-tool-summary") continue;
      const parsed = toolSummaryPayloadSchema.safeParse(part.data);
      if (parsed.success && parsed.data.toolCallId === toolCallId) {
        return parsed.data.summary;
      }
    }
  }
  return null;
}

/** The approval carried by one tool call, across every message in the thread. */
export function findToolApproval(
  messages: UIMessage[],
  toolCallId: string,
): ToolApprovalView | null {
  for (const message of messages) {
    for (const part of message.parts) {
      if (!isToolUIPart(part) || part.toolCallId !== toolCallId) continue;
      const approval = part.approval;
      if (approval === undefined) continue;
      return {
        approvalId: approval.id,
        toolName: getToolName(part),
        input: part.input,
        decision: decisionOf(part.state, approval.approved),
        asked: firstSummaryLine(messages, toolCallId),
      };
    }
  }
  return null;
}

export function ToolApprovalControls({
  toolCallId,
}: {
  toolCallId: string;
}): ReactElement | null {
  const chat = useChatHelpers();
  const { showRaw } = useThreadDevMode();
  const approval = findToolApproval(chat.messages, toolCallId);
  if (approval === null || CARD_TOOLS.has(approval.toolName)) return null;

  const respond = (approved: boolean) => {
    Promise.resolve(
      chat.addToolApprovalResponse({ id: approval.approvalId, approved }),
    ).catch(() => {
      toast.error("Approval could not be sent");
    });
  };

  return (
    <ApprovalCard
      prompt={approvalPromptFor(approval.toolName, approval.asked)}
      input={approval.input}
      showRaw={showRaw}
      onApprove={() => respond(true)}
      onDeny={() => respond(false)}
      decision={approval.decision}
      subject={approvalSubjectFor(approval.toolName, approval.asked)}
    />
  );
}
